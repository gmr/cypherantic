import typing

import neo4j
import pydantic

import cypherantic
from tests import helpers


class CreateRelationshipTests(helpers.TestCase):
    async def test_creates_relationship_with_rel_type_parameter(self) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        alice = Person(name='Alice')
        bob = Person(name='Bob')

        alice_node = await cypherantic.create_node(self.session, alice)
        bob_node = await cypherantic.create_node(self.session, bob)

        created = await cypherantic.create_relationship(
            self.session, alice, bob, rel_type='KNOWS'
        )
        rel = await self.fetch_relationship_by_id(created.element_id)
        self.assertEqual('KNOWS', rel.type)
        self.assertEqual(
            alice_node.element_id,
            helpers.unwrap_as(rel.start_node, neo4j.graph.Node).element_id,
        )
        self.assertEqual(
            bob_node.element_id,
            helpers.unwrap_as(rel.end_node, neo4j.graph.Node).element_id,
        )

    async def test_creates_relationship_with_rel_props_parameter(
        self,
    ) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class Friendship(pydantic.BaseModel):
            since: int

        alice = Person(name='Alice')
        bob = Person(name='Bob')
        friendship = Friendship(since=2020)

        alice_node = await cypherantic.create_node(self.session, alice)
        bob_node = await cypherantic.create_node(self.session, bob)

        created = await cypherantic.create_relationship(
            self.session, alice, bob, friendship
        )

        rel = await self.fetch_relationship_by_id(created.element_id)
        self.assertEqual('Friendship', rel.type)
        self.assertEqual(2020, rel['since'])
        self.assertEqual(
            alice_node.element_id,
            helpers.unwrap_as(rel.start_node, neo4j.graph.Node).element_id,
        )
        self.assertEqual(
            bob_node.element_id,
            helpers.unwrap_as(rel.end_node, neo4j.graph.Node).element_id,
        )

    async def test_creates_relationship_with_custom_rel_type_in_config(
        self,
    ) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class Employment(cypherantic.RelationshipModel):
            cypherantic_config: typing.ClassVar = {'rel_type': 'EMPLOYED_BY'}
            role: str

        employee = Person(name='Alice')
        company = Person(name='TechCorp')
        employment = Employment(role='Engineer')

        employee_node = await cypherantic.create_node(self.session, employee)
        company_node = await cypherantic.create_node(self.session, company)

        created = await cypherantic.create_relationship(
            self.session, employee, company, employment
        )

        rel = await self.fetch_relationship_by_id(created.element_id)
        self.assertEqual('EMPLOYED_BY', rel.type)
        self.assertEqual('Engineer', rel['role'])
        self.assertEqual(
            employee_node.element_id,
            helpers.unwrap_as(rel.start_node, neo4j.graph.Node).element_id,
        )
        self.assertEqual(
            company_node.element_id,
            helpers.unwrap_as(rel.end_node, neo4j.graph.Node).element_id,
        )

    async def test_raises_error_when_neither_rel_type_nor_rel_props_provided(
        self,
    ) -> None:
        class Person(pydantic.BaseModel):
            name: str

        alice = Person(name='Alice')
        bob = Person(name='Bob')

        with self.assertRaises(cypherantic.CypheranticError) as ctx:
            await cypherantic.create_relationship(self.session, alice, bob)  # type: ignore[call-overload]

        self.assertIn(
            'Either rel_cls or rel_type must be provided', str(ctx.exception)
        )

    async def test_creates_relationship_between_nodes_without_unique_fields(
        self,
    ) -> None:
        class Comment(pydantic.BaseModel):
            text: str

        comment1 = Comment(text='First')
        comment2 = Comment(text='Second')

        node1 = await cypherantic.create_node(self.session, comment1)
        node2 = await cypherantic.create_node(self.session, comment2)

        await cypherantic.create_relationship(
            self.session, comment1, comment2, rel_type='REPLIES_TO'
        )

        result = await self.session.run(
            'MATCH (a)-[r:REPLIES_TO]->(b) '
            'WHERE elementId(a) = $id1 AND elementId(b) = $id2 '
            'RETURN r',
            id1=node1.element_id,
            id2=node2.element_id,
        )
        record = await result.single()
        self.assertIsNotNone(record)

    async def test_creates_relationship_with_multiple_unique_fields(
        self,
    ) -> None:
        class Document(pydantic.BaseModel):
            doc_id: typing.Annotated[str, cypherantic.Field(unique=True)]
            version: typing.Annotated[int, cypherantic.Field(unique=True)]

        doc1 = Document(doc_id='DOC-001', version=1)
        doc2 = Document(doc_id='DOC-002', version=1)

        doc1_node = await cypherantic.create_node(self.session, doc1)
        doc2_node = await cypherantic.create_node(self.session, doc2)

        created = await cypherantic.create_relationship(
            self.session, doc1, doc2, rel_type='REFERENCES'
        )

        rel = await self.fetch_relationship_by_id(created.element_id)
        self.assertEqual('REFERENCES', rel.type)
        self.assertEqual(
            doc1_node.element_id,
            helpers.unwrap_as(rel.start_node, neo4j.graph.Node).element_id,
        )
        self.assertEqual(
            doc2_node.element_id,
            helpers.unwrap_as(rel.end_node, neo4j.graph.Node).element_id,
        )

    async def test_creates_relationship_between_nodes_with_custom_labels(
        self,
    ) -> None:
        class Employee(cypherantic.NodeModel):
            cypherantic_config: typing.ClassVar = {
                'labels': ['Person', 'Worker']
            }
            emp_id: typing.Annotated[str, cypherantic.Field(unique=True)]

        class Company(cypherantic.NodeModel):
            cypherantic_config: typing.ClassVar = {
                'labels': ['Organization', 'Business']
            }
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        employee = Employee(emp_id='E123')
        company = Company(name='TechCorp')

        employee_node = await cypherantic.create_node(self.session, employee)
        company_node = await cypherantic.create_node(self.session, company)

        created = await cypherantic.create_relationship(
            self.session, employee, company, rel_type='WORKS_FOR'
        )

        rel = await self.fetch_relationship_by_id(created.element_id)
        self.assertEqual('WORKS_FOR', rel.type)
        self.assertEqual(
            employee_node.element_id,
            helpers.unwrap_as(rel.start_node, neo4j.graph.Node).element_id,
        )
        self.assertEqual(
            company_node.element_id,
            helpers.unwrap_as(rel.end_node, neo4j.graph.Node).element_id,
        )

    async def test_uses_match_clause_with_key_fields_only(self) -> None:
        class User(pydantic.BaseModel):
            user_id: typing.Annotated[str, cypherantic.Field(unique=True)]
            email: str
            name: str

        user1 = User(user_id='U1', email='alice@example.com', name='Alice')
        user2 = User(user_id='U2', email='bob@example.com', name='Bob')

        await cypherantic.create_relationship(
            self.mock_session, user1, user2, rel_type='FOLLOWS'
        )

        call_args = self.mock_session.run.call_args
        params = call_args[1]
        self.assertEqual(params['from_node_props'], {'user_id': 'U1'})
        self.assertEqual(params['to_node_props'], {'user_id': 'U2'})

    async def test_creates_relationship_with_empty_properties(self) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class Connection(pydantic.BaseModel):
            pass

        alice = Person(name='Alice')
        bob = Person(name='Bob')
        connection = Connection()

        alice_node = await cypherantic.create_node(self.session, alice)
        bob_node = await cypherantic.create_node(self.session, bob)

        created = await cypherantic.create_relationship(
            self.session, alice, bob, connection
        )

        rel = await self.fetch_relationship_by_id(created.element_id)
        self.assertEqual('Connection', rel.type)
        self.assertEqual(
            alice_node.element_id,
            helpers.unwrap_as(rel.start_node, neo4j.graph.Node).element_id,
        )
        self.assertEqual(
            bob_node.element_id,
            helpers.unwrap_as(rel.end_node, neo4j.graph.Node).element_id,
        )


class RefreshRelationshipTests(helpers.TestCase):
    async def test_refreshes_outgoing_relationship(self) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class FriendshipProps(cypherantic.RelationshipModel):
            cypherantic_config: typing.ClassVar = {'rel_type': 'FRIENDS_WITH'}
            since: int

        class FriendEdge(typing.NamedTuple):
            node: Person
            properties: FriendshipProps

        class PersonWithFriends(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]
            friends: typing.Annotated[
                list[FriendEdge],
                cypherantic.Relationship(
                    rel_type='FRIENDS_WITH', direction='OUTGOING'
                ),
            ] = []

        alice = PersonWithFriends(name='Alice')
        bob = Person(name='Bob')
        charlie = Person(name='Charlie')

        await cypherantic.create_node(self.session, alice)
        await cypherantic.create_node(self.session, bob)
        await cypherantic.create_node(self.session, charlie)

        await cypherantic.create_relationship(
            self.session, alice, bob, FriendshipProps(since=2020)
        )
        await cypherantic.create_relationship(
            self.session, alice, charlie, FriendshipProps(since=2021)
        )

        await cypherantic.refresh_relationship(self.session, alice, 'friends')

        self.assertEqual(len(alice.friends), 2)
        friend_names = {edge.node.name for edge in alice.friends}
        self.assertSetEqual(friend_names, {'Bob', 'Charlie'})
        friend_years = {edge.properties.since for edge in alice.friends}
        self.assertSetEqual(friend_years, {2020, 2021})

    async def test_refreshes_incoming_relationship(self) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class FollowProps(cypherantic.RelationshipModel):
            cypherantic_config: typing.ClassVar = {'rel_type': 'FOLLOWS'}

        class FollowerEdge(typing.NamedTuple):
            node: Person
            properties: FollowProps

        class PersonWithFollowers(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]
            followers: typing.Annotated[
                list[FollowerEdge],
                cypherantic.Relationship(
                    rel_type='FOLLOWS', direction='INCOMING'
                ),
            ] = []

        alice = PersonWithFollowers(name='Alice')
        bob = Person(name='Bob')
        charlie = Person(name='Charlie')

        await cypherantic.create_node(self.session, alice)
        await cypherantic.create_node(self.session, bob)
        await cypherantic.create_node(self.session, charlie)

        await cypherantic.create_relationship(
            self.session, bob, alice, FollowProps()
        )
        await cypherantic.create_relationship(
            self.session, charlie, alice, FollowProps()
        )

        await cypherantic.refresh_relationship(
            self.session, alice, 'followers'
        )

        self.assertEqual(len(alice.followers), 2)
        follower_names = {edge.node.name for edge in alice.followers}
        self.assertSetEqual(follower_names, {'Bob', 'Charlie'})

    async def test_refreshes_empty_relationship(self) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class FriendshipProps(pydantic.BaseModel):
            since: int

        class FriendEdge(typing.NamedTuple):
            node: Person
            properties: FriendshipProps

        class PersonWithFriends(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]
            friends: typing.Annotated[
                list[FriendEdge],
                cypherantic.Relationship(
                    rel_type='FRIENDS_WITH', direction='OUTGOING'
                ),
            ] = []

        alice = PersonWithFriends(name='Alice')
        await cypherantic.create_node(self.session, alice)

        await cypherantic.refresh_relationship(self.session, alice, 'friends')

        self.assertEqual(len(alice.friends), 0)

    async def test_raises_error_when_property_does_not_exist(self) -> None:
        class Person(pydantic.BaseModel):
            name: str

        person = Person(name='Alice')

        with self.assertRaises(cypherantic.InvalidValueError) as ctx:
            await cypherantic.refresh_relationship(
                self.session, person, 'nonexistent'
            )

        self.assertIn(
            'Relation nonexistent does not exist', str(ctx.exception)
        )

    async def test_raises_error_when_property_is_not_sequence(self) -> None:
        class Person(pydantic.BaseModel):
            name: str
            friend: typing.Annotated[
                dict[str, str],
                cypherantic.Relationship(
                    rel_type='FRIENDS_WITH', direction='OUTGOING'
                ),
            ]

        person = Person(name='Alice', friend={'name': 'Bob'})

        with self.assertRaises(cypherantic.InvalidRelationshipError) as ctx:
            await cypherantic.refresh_relationship(
                self.session, person, 'friend'
            )

        self.assertIn('Relation friend is not a sequence', str(ctx.exception))

    async def test_raises_error_when_property_missing_generic_type(
        self,
    ) -> None:
        class Person(pydantic.BaseModel):
            name: str
            friends: typing.Annotated[  # type: ignore[type-arg]
                list,
                cypherantic.Relationship(
                    rel_type='FRIENDS_WITH', direction='OUTGOING'
                ),
            ] = []

        person = Person(name='Alice')

        with self.assertRaises(cypherantic.InvalidRelationshipError) as ctx:
            await cypherantic.refresh_relationship(
                self.session, person, 'friends'
            )

        self.assertIn(
            'Missing or incorrect generic type for friends',
            str(ctx.exception),
        )

    async def test_raises_error_when_property_missing_relationship_metadata(
        self,
    ) -> None:
        class Person(pydantic.BaseModel):
            name: str

        class FriendEdge(typing.NamedTuple):
            node: Person
            properties: pydantic.BaseModel

        class PersonWithFriends(pydantic.BaseModel):
            name: str
            friends: list[FriendEdge] = []

        person = PersonWithFriends(name='Alice')

        with self.assertRaises(cypherantic.InvalidRelationshipError) as ctx:
            await cypherantic.refresh_relationship(
                self.session, person, 'friends'
            )

        self.assertIn(
            'Missing or incorrect Relationship for friends',
            str(ctx.exception),
        )

    async def test_refreshes_relationship_with_complex_properties(
        self,
    ) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class WorksForProps(cypherantic.RelationshipModel):
            cypherantic_config: typing.ClassVar = {'rel_type': 'WORKS_FOR'}
            role: str
            salary: int
            start_date: str

        class EmploymentEdge(typing.NamedTuple):
            node: Person
            properties: WorksForProps

        class PersonWithEmployer(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]
            employers: typing.Annotated[
                list[EmploymentEdge],
                cypherantic.Relationship(
                    rel_type='WORKS_FOR', direction='OUTGOING'
                ),
            ] = []

        alice = PersonWithEmployer(name='Alice')
        company = Person(name='TechCorp')

        await cypherantic.create_node(self.session, alice)
        await cypherantic.create_node(self.session, company)

        await cypherantic.create_relationship(
            self.session,
            alice,
            company,
            WorksForProps(
                role='Engineer', salary=100000, start_date='2020-01-01'
            ),
        )

        await cypherantic.refresh_relationship(
            self.session, alice, 'employers'
        )

        self.assertEqual(len(alice.employers), 1)
        self.assertEqual(alice.employers[0].node.name, 'TechCorp')
        self.assertEqual(alice.employers[0].properties.role, 'Engineer')
        self.assertEqual(alice.employers[0].properties.salary, 100000)
        self.assertEqual(
            alice.employers[0].properties.start_date, '2020-01-01'
        )


class RetrieveRelationshipEdgesTests(helpers.TestCase):
    async def test_retrieves_outgoing_relationships(self) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class FriendshipProps(cypherantic.RelationshipModel):
            cypherantic_config: typing.ClassVar = {'rel_type': 'FRIENDS_WITH'}
            since: int

        class FriendEdge(typing.NamedTuple):
            node: Person
            properties: FriendshipProps

        alice = Person(name='Alice')
        bob = Person(name='Bob')
        charlie = Person(name='Charlie')

        await cypherantic.create_node(self.session, alice)
        await cypherantic.create_node(self.session, bob)
        await cypherantic.create_node(self.session, charlie)

        await cypherantic.create_relationship(
            self.session, alice, bob, FriendshipProps(since=2020)
        )
        await cypherantic.create_relationship(
            self.session, alice, charlie, FriendshipProps(since=2021)
        )

        results = await cypherantic.retrieve_relationship_edges(
            self.session, alice, 'FRIENDS_WITH', 'OUTGOING', FriendEdge
        )

        self.assertEqual(len(results), 2)
        friend_names = {edge.node.name for edge in results}
        self.assertSetEqual(friend_names, {'Bob', 'Charlie'})
        friend_years = {edge.properties.since for edge in results}
        self.assertSetEqual(friend_years, {2020, 2021})

    async def test_retrieves_incoming_relationships(self) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class FollowProps(cypherantic.RelationshipModel):
            cypherantic_config: typing.ClassVar = {'rel_type': 'FOLLOWS'}
            timestamp: int

        class FollowerEdge(typing.NamedTuple):
            node: Person
            properties: FollowProps

        alice = Person(name='Alice')
        bob = Person(name='Bob')
        charlie = Person(name='Charlie')

        await cypherantic.create_node(self.session, alice)
        await cypherantic.create_node(self.session, bob)
        await cypherantic.create_node(self.session, charlie)

        await cypherantic.create_relationship(
            self.session, bob, alice, FollowProps(timestamp=1000)
        )
        await cypherantic.create_relationship(
            self.session, charlie, alice, FollowProps(timestamp=2000)
        )

        results = await cypherantic.retrieve_relationship_edges(
            self.session, alice, 'FOLLOWS', 'INCOMING', FollowerEdge
        )

        self.assertEqual(len(results), 2)
        follower_names = {edge.node.name for edge in results}
        self.assertSetEqual(follower_names, {'Bob', 'Charlie'})
        timestamps = {edge.properties.timestamp for edge in results}
        self.assertSetEqual(timestamps, {1000, 2000})

    async def test_retrieves_undirected_relationships(self) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class CollaborationProps(cypherantic.RelationshipModel):
            cypherantic_config: typing.ClassVar = {
                'rel_type': 'COLLABORATES_ON'
            }
            project: str

        class CollaborationEdge(typing.NamedTuple):
            node: Person
            properties: CollaborationProps

        alice = Person(name='Alice')
        bob = Person(name='Bob')
        charlie = Person(name='Charlie')

        await cypherantic.create_node(self.session, alice)
        await cypherantic.create_node(self.session, bob)
        await cypherantic.create_node(self.session, charlie)

        await cypherantic.create_relationship(
            self.session,
            alice,
            bob,
            CollaborationProps(project='ProjectA'),
        )
        await cypherantic.create_relationship(
            self.session,
            charlie,
            alice,
            CollaborationProps(project='ProjectB'),
        )

        results = await cypherantic.retrieve_relationship_edges(
            self.session,
            alice,
            'COLLABORATES_ON',
            'UNDIRECTED',
            CollaborationEdge,
        )

        self.assertEqual(len(results), 2)
        collaborator_names = {edge.node.name for edge in results}
        self.assertSetEqual(collaborator_names, {'Bob', 'Charlie'})
        projects = {edge.properties.project for edge in results}
        self.assertSetEqual(projects, {'ProjectA', 'ProjectB'})

    async def test_retrieves_empty_result_set(self) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class FriendshipProps(pydantic.BaseModel):
            since: int

        class FriendEdge(typing.NamedTuple):
            node: Person
            properties: FriendshipProps

        alice = Person(name='Alice')
        await cypherantic.create_node(self.session, alice)

        results = await cypherantic.retrieve_relationship_edges(
            self.session, alice, 'FRIENDS_WITH', 'OUTGOING', FriendEdge
        )

        self.assertEqual(len(results), 0)

    async def test_retrieves_relationships_with_empty_properties(
        self,
    ) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class EmptyProps(cypherantic.RelationshipModel):
            cypherantic_config: typing.ClassVar = {'rel_type': 'CONNECTED_TO'}

        class ConnectionEdge(typing.NamedTuple):
            node: Person
            properties: EmptyProps

        alice = Person(name='Alice')
        bob = Person(name='Bob')

        await cypherantic.create_node(self.session, alice)
        await cypherantic.create_node(self.session, bob)

        await cypherantic.create_relationship(
            self.session, alice, bob, EmptyProps()
        )

        results = await cypherantic.retrieve_relationship_edges(
            self.session, alice, 'CONNECTED_TO', 'OUTGOING', ConnectionEdge
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].node.name, 'Bob')

    async def test_retrieves_relationships_with_complex_properties(
        self,
    ) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class EmploymentProps(cypherantic.RelationshipModel):
            cypherantic_config: typing.ClassVar = {'rel_type': 'WORKS_FOR'}
            role: str
            salary: int
            start_date: str
            benefits: list[str]

        class EmploymentEdge(typing.NamedTuple):
            node: Person
            properties: EmploymentProps

        employee = Person(name='Alice')
        company = Person(name='TechCorp')

        await cypherantic.create_node(self.session, employee)
        await cypherantic.create_node(self.session, company)

        await cypherantic.create_relationship(
            self.session,
            employee,
            company,
            EmploymentProps(
                role='Engineer',
                salary=100000,
                start_date='2020-01-01',
                benefits=['health', 'dental'],
            ),
        )

        results = await cypherantic.retrieve_relationship_edges(
            self.session, employee, 'WORKS_FOR', 'OUTGOING', EmploymentEdge
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].node.name, 'TechCorp')
        self.assertEqual(results[0].properties.role, 'Engineer')
        self.assertEqual(results[0].properties.salary, 100000)
        self.assertEqual(results[0].properties.start_date, '2020-01-01')
        self.assertEqual(results[0].properties.benefits, ['health', 'dental'])

    async def test_retrieves_relationships_with_multiple_unique_fields(
        self,
    ) -> None:
        class Document(pydantic.BaseModel):
            doc_id: typing.Annotated[str, cypherantic.Field(unique=True)]
            version: typing.Annotated[int, cypherantic.Field(unique=True)]

        class ReferenceProps(cypherantic.RelationshipModel):
            cypherantic_config: typing.ClassVar = {'rel_type': 'REFERENCES'}
            page: int

        class ReferenceEdge(typing.NamedTuple):
            node: Document
            properties: ReferenceProps

        doc1 = Document(doc_id='DOC-001', version=1)
        doc2 = Document(doc_id='DOC-002', version=1)
        doc3 = Document(doc_id='DOC-003', version=2)

        await cypherantic.create_node(self.session, doc1)
        await cypherantic.create_node(self.session, doc2)
        await cypherantic.create_node(self.session, doc3)

        await cypherantic.create_relationship(
            self.session, doc1, doc2, ReferenceProps(page=5)
        )
        await cypherantic.create_relationship(
            self.session, doc1, doc3, ReferenceProps(page=10)
        )

        results = await cypherantic.retrieve_relationship_edges(
            self.session, doc1, 'REFERENCES', 'OUTGOING', ReferenceEdge
        )

        self.assertEqual(len(results), 2)
        referenced_docs = {
            (edge.node.doc_id, edge.node.version) for edge in results
        }
        self.assertSetEqual(referenced_docs, {('DOC-002', 1), ('DOC-003', 2)})
        pages = {edge.properties.page for edge in results}
        self.assertSetEqual(pages, {5, 10})

    async def test_retrieves_only_matching_relationship_type(self) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class Props(cypherantic.RelationshipModel):
            cypherantic_config: typing.ClassVar = {'rel_type': 'SPECIFIC_TYPE'}
            value: int

        class Edge(typing.NamedTuple):
            node: Person
            properties: Props

        alice = Person(name='Alice')
        bob = Person(name='Bob')
        charlie = Person(name='Charlie')

        await cypherantic.create_node(self.session, alice)
        await cypherantic.create_node(self.session, bob)
        await cypherantic.create_node(self.session, charlie)

        await cypherantic.create_relationship(
            self.session, alice, bob, Props(value=1)
        )
        await cypherantic.create_relationship(
            self.session, alice, charlie, rel_type='DIFFERENT_TYPE'
        )

        results = await cypherantic.retrieve_relationship_edges(
            self.session, alice, 'SPECIFIC_TYPE', 'OUTGOING', Edge
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].node.name, 'Bob')

    async def test_retrieves_relationships_between_different_node_types(
        self,
    ) -> None:
        class Person(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class Company(pydantic.BaseModel):
            name: typing.Annotated[str, cypherantic.Field(unique=True)]

        class EmploymentProps(cypherantic.RelationshipModel):
            cypherantic_config: typing.ClassVar = {'rel_type': 'WORKS_FOR'}
            role: str

        class EmploymentEdge(typing.NamedTuple):
            node: Company
            properties: EmploymentProps

        employee = Person(name='Alice')
        company1 = Company(name='TechCorp')
        company2 = Company(name='StartupInc')

        await cypherantic.create_node(self.session, employee)
        await cypherantic.create_node(self.session, company1)
        await cypherantic.create_node(self.session, company2)

        await cypherantic.create_relationship(
            self.session, employee, company1, EmploymentProps(role='Engineer')
        )
        await cypherantic.create_relationship(
            self.session,
            employee,
            company2,
            EmploymentProps(role='Consultant'),
        )

        results = await cypherantic.retrieve_relationship_edges(
            self.session, employee, 'WORKS_FOR', 'OUTGOING', EmploymentEdge
        )

        self.assertEqual(len(results), 2)
        company_names = {edge.node.name for edge in results}
        self.assertSetEqual(company_names, {'TechCorp', 'StartupInc'})
        roles = {edge.properties.role for edge in results}
        self.assertSetEqual(roles, {'Engineer', 'Consultant'})
