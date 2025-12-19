# cypherantic

**Pydantic meet Cypher, Cypher meet Pydantic.**

> **⚠️ ALPHA SOFTWARE**: This project is in early development and has not been
> released. The API is subject to change without notice. Use at your own risk.

## Overview

Cypherantic is a Python library that makes interacting with Neo4j simple and
typesafe by leveraging Pydantic models. Define your graph structure using
familiar Pydantic syntax, and let cypherantic handle the Cypher query
generation and type validation.

## Features

- **Type-safe graph modeling**: Use Pydantic models to define nodes and
  relationships with full type checking support
- **Automatic constraint management**: Unique constraints are created
  automatically based on field metadata
- **Relationship traversal**: Navigate graph relationships with simple method
  calls that preserve type information
- **Async-first**: Built on neo4j's async driver for modern Python applications
- **Zero boilerplate**: No manual Cypher query writing for common operations

## Installation

Since this is an unreleased alpha project, install directly from source:

```shell
uv pip install git+https://github.com/yourusername/cypherantic.git
```

## Quick Example

Using the Neo4j movies database as an example:

```python
import typing
import neo4j
import pydantic
import cypherantic


class MovieReviewEdge(typing.NamedTuple):
    node: 'User'
    properties: 'MovieReview'


class Movie(pydantic.BaseModel):
    title: typing.Annotated[str, cypherantic.Field(unique=True)]
    released: typing.Annotated[int, cypherantic.Field(unique=True)]
    tagline: str | None = None
    reviews: typing.Annotated[
        list[MovieReviewEdge],
        cypherantic.Relationship(rel_type='REVIEWED', direction='INCOMING'),
    ] = []


class User(pydantic.BaseModel):
    cypherantic_config: typing.ClassVar[cypherantic.NodeConfig] = {
        'labels': ['Person'],
    }
    name: typing.Annotated[str, cypherantic.Field(unique=True)]


class MovieReview(pydantic.BaseModel):
    cypherantic_config: typing.ClassVar[cypherantic.RelationshipConfig] = {
        'rel_type': 'REVIEWED',
    }
    rating: float
    summary: str


async def main() -> None:
    async with neo4j.AsyncGraphDatabase().driver(
        'bolt://localhost:7687', auth=('neo4j', 'password')
    ) as driver:
        movie = Movie(
            title='Cloud Atlas',
            released=2012,
            tagline='Everything is connected',
        )
        async with driver.session() as session:
            # Load all reviews for the movie
            await cypherantic.refresh_relationship(session, movie, 'reviews')
            for edge in movie.reviews:
                print(f'{edge.node.name}: {edge.properties.rating}/5')
```

## Key Concepts

### Node Models

Define graph nodes using Pydantic models. Use `cypherantic.Field(unique=True)`
to mark properties that should have uniqueness constraints:

```python
class Person(pydantic.BaseModel):
    name: typing.Annotated[str, cypherantic.Field(unique=True)]
    born: int
```

Override the node labels using the `cypherantic_config` class variable:

```python
class User(pydantic.BaseModel):
    cypherantic_config: typing.ClassVar[cypherantic.NodeConfig] = {
        'labels': ['Person', 'User'],
    }
    name: str
```

### Relationship Models

Define relationship properties using Pydantic models with a
`cypherantic_config` that specifies the relationship type:

```python
class ActedIn(pydantic.BaseModel):
    cypherantic_config: typing.ClassVar[cypherantic.RelationshipConfig] = {
        'rel_type': 'ACTED_IN',
    }
    roles: list[str]
```

### Edge Types

Connect nodes and relationship properties using NamedTuples:

```python
class ActedInEdge(typing.NamedTuple):
    node: Movie
    properties: ActedIn
```

### Relationships on Node Models

Declare relationships on node models using the `cypherantic.Relationship`
annotation:

```python
class Actor(pydantic.BaseModel):
    name: str
    movies: typing.Annotated[
        list[ActedInEdge],
        cypherantic.Relationship(rel_type='ACTED_IN', direction='OUTGOING'),
    ] = []
```

## Core API

### Node Operations

- `create_node(session, model)`: Create a node from a Pydantic model
- `unwrap_node_as(model_cls, node)`: Convert a Neo4j node to a Pydantic model

### Relationship Operations

- `create_relationship(session, from_node, to_node, rel_props)`: Create a
  relationship between nodes
- `refresh_relationship(session, model, rel_property)`: Load relationship edges
  into a model's relationship field
- `retrieve_relationship_edges(session, model, rel_name, direction, edge_cls)`:
  Retrieve relationship edges with full type information

## Requirements

- Python 3.12+
- Neo4j 6.0+
- Pydantic 2.12+

## License

BSD-3-Clause License. See `LICENSE` file for details.

## Contributing

Since this is an alpha project, contributions and feedback are welcome. Please
open an issue to discuss proposed changes.
