import os
import typing
from urllib import parse

import dotenv
import neo4j
import pydantic

import cypherantic


class ActedInEdge(typing.NamedTuple):
    node: 'Movie'
    properties: 'Role'


class ReviewedByEdge(typing.NamedTuple):
    node: 'User'
    properties: 'MovieReview'


class MovieReviewEdge(typing.NamedTuple):
    node: 'Movie'
    properties: 'MovieReview'


class Movie(pydantic.BaseModel):
    """Domain model for a Movie node in the graph database."""

    title: typing.Annotated[str, cypherantic.Field(unique=True)]
    released: typing.Annotated[int, cypherantic.Field(unique=True)]
    tagline: str | None = None
    reviews: typing.Annotated[
        list[ReviewedByEdge],
        cypherantic.Relationship(rel_type='REVIEWED', direction='INCOMING'),
    ] = []


class Role(cypherantic.RelationshipModel):
    cypherantic_config: typing.ClassVar = {
        'rel_type': 'ACTED_IN',
    }
    roles: list[str] = []


class User(cypherantic.NodeModel):
    cypherantic_config: typing.ClassVar = {'labels': ['Person']}
    name: typing.Annotated[str, cypherantic.Field(unique=True)]


class Reviewer(User):
    reviews: typing.Annotated[
        list[MovieReviewEdge],
        cypherantic.Relationship(rel_type='REVIEWED', direction='OUTGOING'),
    ] = []


class MovieReview(cypherantic.RelationshipModel):
    cypherantic_config: typing.ClassVar = {'rel_type': 'REVIEWED'}
    rating: float
    summary: str


async def main() -> None:
    dotenv.load_dotenv()
    url = parse.urlsplit(os.environ['NEO4J_URL'])
    assert url.username and url.password
    async with neo4j.AsyncGraphDatabase().driver(
        f'{url.scheme}://{url.hostname}:{url.port or 7687}',
        auth=(url.username, url.password),
    ) as driver:
        await driver.verify_connectivity()
        movie = Movie(
            title='Cloud Atlas',
            released=2012,
            tagline='Everything is connected',
        )
        async with driver.session() as session:
            await cypherantic.refresh_relationship(session, movie, 'reviews')
            for edge in movie.reviews:
                print(edge)

            edges = await cypherantic.retrieve_relationship_edges(
                session,
                User(name='Tom Hanks'),
                'ACTED_IN',
                'OUTGOING',
                ActedInEdge,
            )
            for acted_in in edges:
                print(acted_in)


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
