import os
import unittest.mock
from urllib import parse

import dotenv
import neo4j

import cypherantic

dotenv.load_dotenv()


def unwrap_as[T](value: object | None, target_type: type[T]) -> T:
    if value is None:
        raise AssertionError('Unexpected None value')
    if isinstance(value, target_type):
        return value
    raise AssertionError(f'Expected type {target_type}, got {type(value)}')


class TestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.mock_session = unittest.mock.AsyncMock()
        cypherantic._known_constraints.clear()

        url = parse.urlparse(os.environ.get('NEO4J_URL', 'bolt://127.0.0.1'))
        auth = (unwrap_as(url.username, str), unwrap_as(url.password, str))
        self._driver = await self.enterAsyncContext(
            neo4j.AsyncGraphDatabase().driver(
                f'{url.scheme}://{url.hostname}:{url.port or 7687}', auth=auth
            )
        )
        self._session = await self.enterAsyncContext(self._driver.session())
        self.session = await self._session.begin_transaction()

    async def asyncTearDown(self) -> None:
        await self.session.rollback()
        await super().asyncTearDown()

    async def fetch_node_by_id(self, elm_id: str) -> neo4j.graph.Node:
        result = await self.session.run(
            'MATCH (n) WHERE elementId(n) = $elm_id RETURN n',
            elm_id=elm_id,
        )
        record = await result.single()
        if record and isinstance(record[0], neo4j.graph.Node):
            return record[0]
        raise AssertionError

    async def fetch_relationship_by_id(
        self, elm_id: str
    ) -> neo4j.graph.Relationship:
        result = await self.session.run(
            'MATCH ()-[r]->() WHERE elementId(r) = $elm_id RETURN r',
            elm_id=elm_id,
        )
        record = await result.single()
        if not record or not isinstance(record[0], neo4j.graph.Relationship):
            raise RuntimeError('Failed to create relationship')
        return record[0]
