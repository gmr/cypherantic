import datetime
import typing

import pydantic

import cypherantic
from tests import helpers


class CreateNodeTests(helpers.TestCase):
    async def test_creates_node_with_default_label(self) -> None:
        class Person(pydantic.BaseModel):
            name: str
            age: int

        person = Person(name='Alice', age=30)
        created = await cypherantic.create_node(self.session, person)

        node = await self.fetch_node_by_id(created.element_id)
        from_db = cypherantic.unwrap_node_as(Person, node)
        self.assertEqual(from_db, person)

    async def test_creates_node_with_custom_labels(self) -> None:
        class Employee(pydantic.BaseModel):
            cypherantic_config: typing.ClassVar[cypherantic.NodeConfig] = {
                'labels': ['Person', 'Worker']
            }
            name: str
            employee_id: str

        employee = Employee(name='Bob', employee_id='E123')
        created = await cypherantic.create_node(self.session, employee)

        node = await self.fetch_node_by_id(created.element_id)
        self.assertSetEqual({'Person', 'Worker'}, node.labels)

    async def test_excludes_relationship_fields_from_properties(self) -> None:
        class Company(pydantic.BaseModel):
            name: str
            employees: typing.Annotated[
                list[object],
                cypherantic.Relationship(
                    rel_type='WORKS_FOR', direction='INCOMING'
                ),
            ] = []

        company = Company(name='TechCorp')
        created = await cypherantic.create_node(self.session, company)
        node = await self.fetch_node_by_id(created.element_id)
        self.assertNotIn('employees', node)

    async def test_creates_unique_constraint_for_unique_field(self) -> None:
        class User(pydantic.BaseModel):
            username: typing.Annotated[str, cypherantic.Field(unique=True)]
            email: str

        user = User(username='alice', email='alice@example.com')
        await cypherantic.create_node(self.mock_session, user)
        for call_info in self.mock_session.run.call_args_list:
            query = call_info[0][0]
            if query.startswith('CREATE CONSTRAINT User_unique'):
                self.assertIn('n.username', query)
                self.assertNotIn('n.email', query)
                break
        else:
            self.fail('Unique constraint creation query not found.')

    async def test_creates_constraint_with_multiple_unique_fields(
        self,
    ) -> None:
        class Document(pydantic.BaseModel):
            doc_id: typing.Annotated[str, cypherantic.Field(unique=True)]
            version: typing.Annotated[int, cypherantic.Field(unique=True)]
            content: str

        doc = Document(doc_id='DOC-001', version=1, content='Hello')
        await cypherantic.create_node(self.mock_session, doc)
        for call_info in self.mock_session.run.call_args_list:
            query = call_info[0][0]
            if query.startswith('CREATE CONSTRAINT Document_unique'):
                self.assertIn('n.doc_id', query)
                self.assertIn('n.version', query)
                self.assertNotIn('n.content', query)
                break
        else:
            self.fail('Unique constraint creation query not found.')

    async def test_does_not_create_constraint_twice_for_same_model(
        self,
    ) -> None:
        class Product(pydantic.BaseModel):
            sku: typing.Annotated[str, cypherantic.Field(unique=True)]
            name: str

        product1 = Product(sku='SKU-001', name='Widget')
        product2 = Product(sku='SKU-002', name='Gadget')

        await cypherantic.create_node(self.mock_session, product1)
        await cypherantic.create_node(self.mock_session, product2)

        constraint_calls = [
            call
            for call in self.mock_session.run.call_args_list
            if 'CREATE CONSTRAINT' in call[0][0]
        ]
        self.assertEqual(len(constraint_calls), 1)

    async def test_creates_node_without_unique_fields(self) -> None:
        class Comment(pydantic.BaseModel):
            text: str
            timestamp: int

        comment = Comment(text='Great post!', timestamp=1234567890)
        await cypherantic.create_node(self.mock_session, comment)

        self.mock_session.run.assert_called_once()
        call_args = self.mock_session.run.call_args
        query = call_args[0][0]
        self.assertNotIn('CREATE CONSTRAINT', query)
        self.assertIn('CREATE (n:Comment $properties)', query)

    async def test_handles_empty_model_fields(self) -> None:
        class EmptyNode(pydantic.BaseModel):
            pass

        empty = EmptyNode()
        created = await cypherantic.create_node(self.session, empty)
        node = await self.fetch_node_by_id(created.element_id)
        self.assertDictEqual({}, dict(node))

    async def test_handles_datetime_fields(self) -> None:
        class Event(pydantic.BaseModel):
            name: str
            occurred_at: datetime.datetime

        event = Event(
            name='Launch',
            occurred_at=datetime.datetime(
                2024, 1, 1, 12, 0, 0, tzinfo=datetime.UTC
            ),
        )
        created = await cypherantic.create_node(self.session, event)

        node = await self.fetch_node_by_id(created.element_id)
        from_db = cypherantic.unwrap_node_as(Event, node)
        self.assertEqual(from_db.name, 'Launch')
        self.assertEqual(
            from_db.occurred_at,
            datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.UTC),
        )

    async def test_handles_node_with_required_relationship_field(self) -> None:
        class User(pydantic.BaseModel):
            name: str

        class Token(pydantic.BaseModel):
            jti: str
            user: typing.Annotated[
                User | None,
                cypherantic.Relationship(
                    rel_type='ISSUED_TO', direction='OUTGOING'
                ),
            ] = None

        token = Token(jti='token123', user=None)
        created = await cypherantic.create_node(self.session, token)

        node = await self.fetch_node_by_id(created.element_id)
        from_db = cypherantic.unwrap_node_as(Token, node)
        self.assertEqual(from_db.jti, 'token123')
        self.assertIsNone(from_db.user)

    async def test_handles_node_with_list_relationship_field(self) -> None:
        class Post(pydantic.BaseModel):
            title: str

        class Comment(pydantic.BaseModel):
            text: str

        class PostWithComments(pydantic.BaseModel):
            title: str
            comments: typing.Annotated[
                list[Comment],
                cypherantic.Relationship(
                    rel_type='HAS_COMMENT', direction='OUTGOING'
                ),
            ] = []

        post = PostWithComments(title='Hello World', comments=[])
        created = await cypherantic.create_node(self.session, post)

        node = await self.fetch_node_by_id(created.element_id)
        from_db = cypherantic.unwrap_node_as(PostWithComments, node)
        self.assertEqual(from_db.title, 'Hello World')
        self.assertEqual(from_db.comments, [])
