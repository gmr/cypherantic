import inspect
import json
import logging
import typing
from collections import abc

import neo4j.graph
import pydantic.dataclasses
import pydantic.fields

_known_constraints: set[type[pydantic.BaseModel]] = set()


class CypheranticError(Exception):
    pass


class InvalidValueError(CypheranticError, ValueError):
    pass


class InvalidRelationshipError(InvalidValueError):
    pass


class SessionType(typing.Protocol):
    async def run(
        self,
        query: typing.LiteralString,
        parameters: dict[str, typing.Any] | None = None,
        **kwargs: object,
    ) -> neo4j.AsyncResult: ...


ModelType = typing.TypeVar('ModelType', bound=pydantic.BaseModel)
SourceNode = typing.TypeVar('SourceNode', bound=pydantic.BaseModel)
TargetNode = typing.TypeVar('TargetNode', bound=pydantic.BaseModel)
RelationshipProperties = typing.TypeVar(
    'RelationshipProperties', bound=pydantic.BaseModel
)
EdgeType = typing.TypeVar('EdgeType')


class NodeConfig(typing.TypedDict, total=False):
    labels: typing.NotRequired[list[str]]


class NodeModel(pydantic.BaseModel):
    cypherantic_config: typing.ClassVar[NodeConfig] = {}


class RelationshipConfig(typing.TypedDict, total=False):
    rel_type: typing.NotRequired[str]


class RelationshipModel(pydantic.BaseModel):
    cypherantic_config: typing.ClassVar[RelationshipConfig] = {}


@pydantic.dataclasses.dataclass(frozen=True)
class Field:
    unique: bool = False


@pydantic.dataclasses.dataclass(frozen=True)
class Relationship:
    rel_type: str
    direction: typing.Literal['INCOMING', 'OUTGOING']


def unwrap_node_as(
    model_cls: type[ModelType], node: neo4j.graph.Node | None
) -> ModelType:
    if node is None:
        raise InvalidValueError('No record to unwrap')
    return model_cls.model_validate(node)


async def unwrap_result_as_node(
    model_cls: type[ModelType], result: neo4j.AsyncResult
) -> ModelType:
    record = await result.single()
    if record is None or len(record) == 0:
        raise InvalidValueError('Record is empty')
    if len(record) != 1:
        raise InvalidValueError('Too many nodes in record')
    return unwrap_node_as(model_cls, record[0])


async def create_node(
    session: SessionType, model: ModelType
) -> neo4j.graph.Node:
    model_cls = type(model)
    config = typing.cast(
        'NodeConfig', getattr(model, 'cypherantic_config', {})
    )
    try:
        node_labels = config['labels']
    except (IndexError, KeyError):
        node_labels = [model_cls.__name__]

    if model_cls not in _known_constraints:
        await _ensure_constraints(session, model_cls, node_labels)

    properties: dict[str, object] = {}
    for field_name, field_value in model.model_dump(mode='python').items():
        for md in model_cls.model_fields[field_name].metadata:
            if isinstance(md, Relationship):
                break
        else:
            properties[field_name] = field_value

    query = f'CREATE (n:{"&".join(node_labels)} $properties) RETURN n'
    result = await _instrumented_run(session, query, properties=properties)
    record = await result.single()
    if record is None:  # pragma: no cover
        raise CypheranticError('Failed to create node')
    return typing.cast('neo4j.graph.Node', record[0])


@typing.overload
async def create_relationship(
    session: SessionType,
    from_node: SourceNode,
    to_node: TargetNode,
    rel_props: RelationshipProperties,
) -> neo4j.graph.Relationship: ...


@typing.overload
async def create_relationship(
    session: SessionType,
    from_node: SourceNode,
    to_node: TargetNode,
    *,
    rel_type: str,
) -> neo4j.graph.Relationship: ...


async def create_relationship(
    session: SessionType,
    from_node: SourceNode,
    to_node: TargetNode,
    rel_props: RelationshipProperties | None = None,
    *,
    rel_type: str | None = None,
) -> neo4j.graph.Relationship:
    if rel_type is not None:
        rel_name = rel_type
    elif rel_props is not None:
        rel_cls = type(rel_props)
        config = typing.cast(
            'RelationshipConfig', getattr(rel_cls, 'cypherantic_config', {})
        )
        rel_name = config.get('rel_type', rel_cls.__name__)
    else:
        raise CypheranticError('Either rel_cls or rel_type must be provided')

    from_node_cls = type(from_node)
    to_node_cls = type(to_node)

    parameters: dict[str, typing.Any] = {
        'from_node_props': {},
        'rel_name': rel_name,
        'rel_props': {},
        'to_node_props': {},
    }
    source_labels = '&'.join(_extract_labels(from_node_cls))
    target_labels = '&'.join(_extract_labels(to_node_cls))
    if key_fields := _extract_key_fields(from_node_cls):
        parameters['from_node_props'] = {
            field: getattr(from_node, field) for field in key_fields
        }
    if key_fields := _extract_key_fields(to_node_cls):
        parameters['to_node_props'] = {
            field: getattr(to_node, field) for field in key_fields
        }
    if rel_props is not None:
        parameters['rel_props'] = rel_props.model_dump(mode='python')

    source_match = _build_match_clause(from_node_cls, 'from_node_props')
    target_match = _build_match_clause(to_node_cls, 'to_node_props')

    # Note that using dynamic labels in Cypher queries is not well optimized,
    # so I am sticking with static labels here.
    # See https://neo4j.com/docs/cypher-manual/current/clauses/match/#dynamic-match-caveats
    result = await _instrumented_run(
        session,
        f'MATCH (a:{source_labels} {source_match})'
        ' WITH a '
        f'MATCH (b:{target_labels} {target_match})'
        ' CREATE (a)-[r:$($rel_name) $rel_props]->(b)'
        ' RETURN r',
        **parameters,
    )
    record = await result.single()
    if record is None:  # pragma: no cover
        raise CypheranticError('Failed to create relationship')
    return typing.cast('neo4j.graph.Relationship', record[0])


async def refresh_relationship(
    session: SessionType,
    model: SourceNode,
    rel_property: str,
) -> None:
    model_cls = type(model)
    try:
        field: pydantic.fields.FieldInfo = model_cls.model_fields[rel_property]
    except KeyError:
        raise InvalidValueError(
            f'Relation {rel_property} does not exist'
        ) from None

    origin = typing.get_origin(field.annotation)
    if not origin:
        raise InvalidRelationshipError(
            f'Missing or incorrect generic type for {rel_property}'
        )

    if not issubclass(origin, abc.Sequence):
        raise InvalidRelationshipError(
            f'Relation {rel_property} is not a sequence'
        )

    anno_args = typing.get_args(field.annotation)

    rel_data = [md for md in field.metadata if isinstance(md, Relationship)]
    if len(rel_data) != 1:
        raise InvalidRelationshipError(
            f'Missing or incorrect Relationship for {rel_property}'
        )

    results = await retrieve_relationship_edges(
        session,
        model,
        rel_data[0].rel_type,
        rel_data[0].direction,
        anno_args[0],
    )
    setattr(model, rel_property, results)


async def retrieve_relationship_edges(
    session: SessionType,
    model: SourceNode,
    rel_name: str,
    direction: typing.Literal['INCOMING', 'OUTGOING', 'UNDIRECTED'],
    edge_cls: type[EdgeType],
) -> list[EdgeType]:
    tuple_cls = edge_cls
    target_cls, prop_cls = _validate_edge_type(edge_cls)

    parameters: dict[str, typing.Any] = {
        'from_node_props': {},
        'rel_name': rel_name,
    }
    source_labels = '&'.join(_extract_labels(type(model)))
    if key_fields := _extract_key_fields(type(model)):
        parameters['from_node_props'] = {
            field: getattr(model, field) for field in key_fields
        }
    source_match = _build_match_clause(type(model), 'from_node_props')

    query = ''
    if direction == 'INCOMING':
        query = (
            f'MATCH (b)-[r:$($rel_name)]->(a:{source_labels} {source_match})'
            f' RETURN r, b'
        )
    elif direction == 'OUTGOING':
        query = (
            f'MATCH (a:{source_labels} {source_match})-[r:$($rel_name)]->(b)'
            f' RETURN r, b'
        )
    else:  # UNDIRECTED
        query = (
            f'MATCH (a:{source_labels} {source_match})-[r:$($rel_name)]-(b)'
            f' RETURN r, b'
        )
    result = await _instrumented_run(session, query, **parameters)
    results: list[EdgeType] = []
    async for record in result:
        rel_instance = prop_cls.model_validate(record['r'])
        node_instance = target_cls.model_validate(record['b'])
        results.append(tuple_cls(node=node_instance, properties=rel_instance))  # type: ignore[call-arg]
    return results


def _build_match_clause(model_cls: type[ModelType], param_alias: str) -> str:
    match_props = {
        field: f'${param_alias}.{field}'
        for field in _extract_key_fields(model_cls)
    }
    if match_props:
        return '{{{}}}'.format(
            ','.join(f'{key}:{value}' for key, value in match_props.items())
        )
    return ''


def _extract_labels(model_cls: type[pydantic.BaseModel]) -> list[str]:
    config = typing.cast(
        'NodeConfig', getattr(model_cls, 'cypherantic_config', {})
    )
    try:
        return config['labels']
    except KeyError:
        return [model_cls.__name__]


def _extract_key_fields(model_cls: type[pydantic.BaseModel]) -> list[str]:
    key_fields = []
    for field_name, field_info in model_cls.model_fields.items():
        for md in field_info.metadata:
            if isinstance(md, Field) and md.unique:
                key_fields.append(field_name)
    return key_fields


async def _ensure_constraints(
    session: SessionType,
    model_cls: type[pydantic.BaseModel],
    node_labels: abc.Sequence[str],
) -> None:
    if isinstance(session, neo4j.AsyncTransaction):
        return

    if not node_labels or model_cls in _known_constraints:
        return

    unique_constraints = []
    for field_name, field_info in model_cls.model_fields.items():
        for md in field_info.metadata:
            if isinstance(md, Field) and md.unique:
                unique_constraints.append(field_name)
    if unique_constraints:
        constraint_name = f'{model_cls.__name__}_unique'
        props = ', '.join(f'n.{prop}' for prop in unique_constraints)
        query = (
            f'CREATE CONSTRAINT {constraint_name} IF NOT EXISTS '
            f'FOR (n:{node_labels[0]}) REQUIRE ({props}) IS UNIQUE'
        )
        await _instrumented_run(session, query)
    _known_constraints.add(model_cls)


async def _instrumented_run(
    session: SessionType, query: str, **parameters: object
) -> neo4j.AsyncResult:
    logger = logging.getLogger('cypherantic')
    logger.debug('Executing query: %s', query)
    logger.debug('With parameters: %s', json.dumps(parameters, indent=None))
    return await session.run(query, **parameters)  # type: ignore[arg-type]


def _validate_edge_type(
    tp: typing.Callable[..., object],
) -> tuple[type[pydantic.BaseModel], type[pydantic.BaseModel]]:
    type_info = typing.get_type_hints(tp)
    if 'node' not in type_info or 'properties' not in type_info:
        raise TypeError(
            'Edge type must have "node" and "properties" attributes'
        )
    if not issubclass(type_info['node'], pydantic.BaseModel):
        raise TypeError(
            '"node" attribute must be a pydantic BaseModel subclass'
        )
    if not issubclass(type_info['properties'], pydantic.BaseModel):
        raise TypeError(
            '"properties" attribute must be a pydantic BaseModel subclass'
        )

    sig = inspect.signature(tp)
    if 'node' not in sig.parameters or 'properties' not in sig.parameters:
        raise TypeError(
            'Edge type must have "node" and "properties" parameters in'
            ' its initializer'
        )

    return type_info['node'], type_info['properties']


# Wrap lookup functions in caches to improve performance. This is
# done conditionally since functools.cache does not preserve the
# function signature, which is important for type checking.
# https://github.com/python/typeshed/issues/11280
# https://github.com/python/typing/discussions/946
if not typing.TYPE_CHECKING:  # pragma: no cover
    import functools

    _build_match_clause = functools.cache(_build_match_clause)
    _extract_labels = functools.cache(_extract_labels)
    _extract_key_fields = functools.cache(_extract_key_fields)
    _validate_edge_type = functools.cache(_validate_edge_type)
