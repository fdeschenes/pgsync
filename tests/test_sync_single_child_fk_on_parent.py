"""Tests for `pgsync` package."""

import mock
import psycopg2
import pytest

from pgsync.base import subtransactions
from pgsync.exc import (
    ForeignKeyError,
    RelationshipAttributeError,
    RelationshipError,
    RelationshipTypeError,
    RelationshipVariantError,
)
from pgsync.node import Tree
from pgsync.sync import Sync

from .helpers.utils import assert_resync_empty, search, truncate_slots


@pytest.mark.usefixtures('table_creator')
class TestParentSingleChildFkOnParent(object):
    """Root and single child node tests."""

    @pytest.fixture(scope='function')
    def data(self, sync, book_cls, publisher_cls):

        session = sync.session

        books = [
            book_cls(
                isbn='abc',
                title='The Tiger Club',
                description='Tigers are fierce creatures',
                publisher=publisher_cls(id=1, name='Tiger publishing'),
            ),
            book_cls(
                isbn='def',
                title='The Lion Club',
                description='Lion and the mouse',
                publisher=publisher_cls(id=2, name='Lion publishing'),
            ),
            book_cls(
                isbn='ghi',
                title='The Rabbit Club',
                description='Rabbits on the run',
                publisher=publisher_cls(id=3, name='Hop Bunny publishing'),
            )
        ]

        with subtransactions(session):
            session.add_all(books)

        sync.logical_slot_get_changes(
            f'{sync.database}_testdb',
            upto_nchanges=None,
        )

        yield books

        with subtransactions(session):
            conn = session.connection().engine.connect().connection
            conn.set_isolation_level(
                psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT
            )
            cursor = conn.cursor()
            channel = session.connection().engine.url.database
            cursor.execute(f'UNLISTEN {channel}')

        with subtransactions(session):
            sync.truncate_tables(
                [
                    book_cls.__table__.name,
                    publisher_cls.__table__.name
                ]
            )

        sync.logical_slot_get_changes(
            f'{sync.database}_testdb',
            upto_nchanges=None,
        )

        try:
            sync.es.teardown(index='testdb')
        except Exception:
            raise

        sync.redis._delete()
        session.connection().engine.connect().close()
        session.connection().engine.dispose()

    def test_relationship_object_one_to_one(self, sync, data):
        nodes = [{
            'table': 'book',
            'columns': ['isbn', 'title', 'description'],
            'children':[{
                'table': 'publisher',
                'columns': ['id', 'name'],
                'relationship': {
                    'variant': 'object',
                    'type': 'one_to_one'
                }
            }]
        }]
        docs = [doc for doc in sync._sync(nodes, 'testdb')]
        assert docs[0]['_id'] == u'abc'
        assert docs[0]['_source'] == {
            '_meta': {
                'publisher': {'id': [1]}
            },
            u'description': u'Tigers are fierce creatures',
            u'isbn': u'abc',
            'publisher': {
                'id': 1,
                'name': 'Tiger publishing'
            },
            u'title': u'The Tiger Club'
        }

        assert docs[1]['_id'] == u'def'
        assert docs[1]['_source'] == {
            '_meta': {
                'publisher': {'id': [2]}
            },
            u'description': u'Lion and the mouse',
            u'isbn': u'def',
            'publisher': {
                'id': 2,
                'name': 'Lion publishing'
            },
            u'title': u'The Lion Club'
        }

        assert docs[2]['_id'] == u'ghi'
        assert docs[2]['_source'] == {
            '_meta': {
                'publisher': {'id': [3]}
            },
            u'description': u'Rabbits on the run',
            u'isbn': u'ghi',
            'publisher': {
                'id': 3,
                'name': 'Hop Bunny publishing'
            },
            u'title': u'The Rabbit Club'
        }
        assert_resync_empty(sync, nodes, 'testdb')

    def test_relationship_object_one_to_many(self, sync, data):
        nodes = [{
            'table': 'book',
            'columns': ['isbn', 'title', 'description'],
            'children':[{
                'table': 'publisher',
                'columns': ['name', 'id'],
                'relationship': {
                    'variant': 'object',
                    'type': 'one_to_many'
                }
            }]
        }]
        docs = [doc for doc in sync._sync(nodes, 'testdb')]

        assert docs[0]['_id'] == u'abc'
        assert docs[0]['_source'] == {
            '_meta': {
                'publisher': {'id': [1]}
            },
            u'description': u'Tigers are fierce creatures',
            u'isbn': u'abc',
            'publisher': [
                {'id': 1, 'name': 'Tiger publishing'}
            ],
            u'title': u'The Tiger Club'
        }

        assert docs[1]['_id'] == u'def'
        assert docs[1]['_source'] == {
            '_meta': {
                'publisher': {'id': [2]}
            },
            u'description': u'Lion and the mouse',
            u'isbn': u'def',
            'publisher': [
                {'id': 2, 'name': 'Lion publishing'}
            ],
            u'title': u'The Lion Club'
        }

        assert docs[2]['_id'] == u'ghi'
        assert docs[2]['_source'] == {
            '_meta': {
                'publisher': {'id': [3]}
            },
            u'description': u'Rabbits on the run',
            u'isbn': u'ghi',
            'publisher': [
                {'id': 3, 'name': 'Hop Bunny publishing'}
            ],
            u'title': u'The Rabbit Club'
        }
        assert_resync_empty(sync, nodes, 'testdb')

    def test_relationship_scalar_one_to_one(self, sync, data):
        nodes = [{
            'table': 'book',
            'columns': ['isbn', 'title', 'description'],
            'children':[{
                'table': 'publisher',
                'columns': ['name'],
                'relationship': {
                    'variant': 'scalar',
                    'type': 'one_to_one'
                }
            }]
        }]
        docs = [doc for doc in sync._sync(nodes, 'testdb')]
        assert docs[0]['_id'] == u'abc'
        assert docs[0]['_source'] == {
            '_meta': {
                'publisher': {'id': [1]}
            },
            u'description': u'Tigers are fierce creatures',
            u'isbn': u'abc',
            'publisher': 'Tiger publishing',
            u'title': u'The Tiger Club'
        }

        assert docs[1]['_id'] == u'def'
        assert docs[1]['_source'] == {
            '_meta': {
                'publisher': {'id': [2]}
            },
            u'description': u'Lion and the mouse',
            u'isbn': u'def',
            'publisher': 'Lion publishing',
            u'title': u'The Lion Club'
        }

        assert docs[2]['_id'] == u'ghi'
        assert docs[2]['_source'] == {
            '_meta': {
                'publisher': {'id': [3]}
            },
            u'description': u'Rabbits on the run',
            u'isbn': u'ghi',
            'publisher': 'Hop Bunny publishing',
            u'title': u'The Rabbit Club'
        }
        assert_resync_empty(sync, nodes, 'testdb')

    def test_relationship_scalar_one_to_many(self, sync, data):
        nodes = [{
            'table': 'book',
            'columns': ['isbn', 'title', 'description'],
            'children':[{
                'table': 'publisher',
                'columns': ['name'],
                'relationship': {
                    'variant': 'scalar',
                    'type': 'one_to_many'
                }
            }]
        }]
        docs = [doc for doc in sync._sync(nodes, 'testdb')]
        assert docs[0]['_id'] == u'abc'
        assert docs[0]['_source'] == {
            '_meta': {
                'publisher': {'id': [1]}
            },
            u'description': u'Tigers are fierce creatures',
            u'isbn': u'abc',
            'publisher': ['Tiger publishing'],
            u'title': u'The Tiger Club'
        }

        assert docs[1]['_id'] == u'def'
        assert docs[1]['_source'] == {
            '_meta': {
                'publisher': {'id': [2]}
            },
            u'description': u'Lion and the mouse',
            u'isbn': u'def',
            'publisher': ['Lion publishing'],
            u'title': u'The Lion Club'
        }

        assert docs[2]['_id'] == u'ghi'
        assert docs[2]['_source'] == {
            '_meta': {
                'publisher': {'id': [3]}
            },
            u'description': u'Rabbits on the run',
            u'isbn': u'ghi',
            'publisher': ['Hop Bunny publishing'],
            u'title': u'The Rabbit Club'
        }
        assert_resync_empty(sync, nodes, 'testdb')

    def test_label(self, sync, data):
        nodes = [{
            'table': 'book',
            'columns': ['isbn', 'title', 'description'],
            'children':[{
                'table': 'publisher',
                'label': 'publisher_x',
                'columns': ['name'],
                'relationship': {
                    'variant': 'scalar',
                    'type': 'one_to_one'
                }
            }]
        }]
        docs = [doc for doc in sync._sync(nodes, 'testdb')]
        assert docs[0]['_id'] == u'abc'
        assert docs[0]['_source'] == {
            '_meta': {
                'publisher': {'id': [1]}
            },
            u'description': u'Tigers are fierce creatures',
            u'isbn': u'abc',
            u'publisher_x': 'Tiger publishing',
            u'title': u'The Tiger Club'
        }

        assert docs[1]['_id'] == u'def'
        assert docs[1]['_source'] == {
            '_meta': {
                'publisher': {'id': [2]}
            },
            u'description': u'Lion and the mouse',
            u'isbn': u'def',
            u'publisher_x': 'Lion publishing',
            u'title': u'The Lion Club'
        }

        assert docs[2]['_id'] == u'ghi'
        assert docs[2]['_source'] == {
            '_meta': {
                'publisher': {'id': [3]}
            },
            u'description': u'Rabbits on the run',
            u'isbn': u'ghi',
            u'publisher_x': 'Hop Bunny publishing',
            u'title': u'The Rabbit Club'
        }
        assert_resync_empty(sync, nodes, 'testdb')

    def test_null_label(self, sync, data):
        """ null label should revert back to the table name
        """
        nodes = [{
            'table': 'book',
            'columns': ['isbn', 'title', 'description'],
            'children':[{
                'table': 'publisher',
                'label': None,
                'columns': ['name'],
                'relationship': {
                    'variant': 'scalar',
                    'type': 'one_to_one'
                }
            }]
        }]
        docs = [doc for doc in sync._sync(nodes, 'testdb')]
        assert docs[0]['_id'] == u'abc'
        assert docs[0]['_source'] == {
            '_meta': {
                'publisher': {'id': [1]}
            },
            u'description': u'Tigers are fierce creatures',
            u'isbn': u'abc',
            u'publisher': 'Tiger publishing',
            u'title': u'The Tiger Club'
        }
        assert_resync_empty(sync, nodes, 'testdb')

    def test_transform(self, sync, data):
        nodes = [{
            'table': 'book',
            'columns': ['isbn', 'title', 'description'],
            'transform': {
                'rename': {
                    'isbn': 'book_isbn',
                    'title': 'book_title'
                }
            },
            'children': [{
                'table': 'publisher',
                'columns': ['id', 'name'],
                'transform': {
                    'rename': {
                        'id': 'publisher_id',
                        'name': 'publisher_name'
                    }
                },
                'relationship': {
                    'variant': 'object',
                    'type': 'one_to_one'
                }
            }]
        }]
        docs = [doc for doc in sync._sync(nodes, 'testdb')]
        assert docs[0]['_id'] == u'abc'
        assert docs[0]['_source'] == {
            '_meta': {
                'publisher': {'id': [1]}
            },
            'book_isbn': 'abc',
            'book_title': 'The Tiger Club',
            'description': 'Tigers are fierce creatures',
            'publisher': {
                'publisher_id': 1,
                'publisher_name': 'Tiger publishing'
            }
        }

        assert docs[1]['_id'] == u'def'
        assert docs[1]['_source'] == {
            '_meta': {
                'publisher': {'id': [2]}
            },
            'book_isbn': 'def',
            'book_title': 'The Lion Club',
            'description': 'Lion and the mouse',
            'publisher': {
                'publisher_id': 2,
                'publisher_name': 'Lion publishing'
            }
        }

        assert docs[2]['_id'] == u'ghi'
        assert docs[2]['_source'] == {
            '_meta': {
                'publisher': {'id': [3]}
            },
            'book_isbn': 'ghi',
            'book_title': 'The Rabbit Club',
            'description': 'Rabbits on the run',
            'publisher': {
                'publisher_id': 3,
                'publisher_name': 'Hop Bunny publishing'
            }
        }
        assert_resync_empty(sync, nodes, 'testdb')

    def test_schema(self, sync, data):
        nodes = [{
            'table': 'book',
            'columns': ['isbn', 'title', 'description'],
            'children': [{
                'table': 'publisher',
                'columns': ['id', 'name'],
                'relationship': {
                    'variant': 'object',
                    'type': 'one_to_one'
                }
            }]
        }]
        docs = [doc for doc in sync._sync(nodes, 'testdb')]

        fields = [
            '_meta', 'description', 'isbn', 'publisher', 'title'
        ]
        assert sorted(docs[0]['_source'].keys()) == sorted(fields)
        assert sorted(docs[1]['_source'].keys()) == sorted(fields)
        assert sorted(docs[0]['_source']['publisher'].keys()) == sorted(
            ['id', 'name']
        )
        assert sorted(docs[1]['_source']['publisher'].keys()) == sorted(
            ['id', 'name']
        )
        assert_resync_empty(sync, nodes, 'testdb')

    def test_schema_with_no_column_specified(self, sync, data):
        nodes = [{
            'table': 'book',
            'children': [{
                'table': 'publisher',
                'relationship': {
                    'variant': 'object',
                    'type': 'one_to_one'
                }
            }]
        }]
        docs = [doc for doc in sync._sync(nodes, 'testdb')]
        assert docs[2]['_source'] == {
            '_meta': {'publisher': {'id': [3]}},
            'copyright': None,
            'description': 'Rabbits on the run',
            'isbn': 'ghi',
            'publisher': {
                'id': 3,
                'name': 'Hop Bunny publishing'
            },
            'publisher_id': 3,
            'title': 'The Rabbit Club'
        }
        assert_resync_empty(sync, nodes, 'testdb')

    def test_invalid_relationship_type(self, sync):
        nodes = [{
            'table': 'book',
            'children': [{
                'table': 'publisher',
                'relationship': {
                    'variant': 'object',
                    'type': 'qwerty'
                }
            }]
        }]
        with pytest.raises(RelationshipTypeError) as excinfo:
            Tree(sync).build(nodes[0])
        assert 'Relationship type "qwerty" is invalid' in str(
            excinfo.value
        )

    def test_invalid_relationship_variant(self, sync):
        nodes = [{
            'table': 'book',
            'children': [{
                'table': 'publisher',
                'relationship': {
                    'variant': 'abcdefg',
                    'type': 'one_to_one'
                }
            }]
        }]
        with pytest.raises(RelationshipVariantError) as excinfo:
            Tree(sync).build(nodes[0])
        assert 'Relationship variant "abcdefg" is invalid' in str(
            excinfo.value
        )

    def test_invalid_relationship_attribute(self, sync):
        nodes = [{
            'table': 'book',
            'children': [{
                'table': 'publisher',
                'relationship': {
                    'foo': 'object',
                    'type': 'one_to_one'
                }
            }]
        }]
        with pytest.raises(RelationshipAttributeError) as excinfo:
            Tree(sync).build(nodes[0])
        assert f"Relationship attribute {set(['foo'])} is invalid" in str(
            excinfo.value
        )

    def test_meta_keys(self, sync, data):
        """Private keys should be correct"""
        nodes = [{
            'table': 'book',
            'children': [{
                'table': 'publisher',
                'relationship': {
                    'variant': 'object',
                    'type': 'one_to_one'
                }
            }]
        }]
        docs = [doc for doc in sync._sync(nodes, 'testdb')]
        sources = {doc['_id']: doc['_source'] for doc in docs}
        assert sources['abc']['_meta'] == {'publisher': {'id': [1]}}
        assert sources['def']['_meta'] == {'publisher': {'id': [2]}}
        assert sources['ghi']['_meta'] == {'publisher': {'id': [3]}}
        assert_resync_empty(sync, nodes, 'testdb')

    def test_missing_foreign_keys(self, sync, data):
        """Foreign keys must be present between parent and child"""
        nodes = [{
            'table': 'book',
            'children': [{
                'table': 'city',
                'relationship': {
                    'variant': 'object',
                    'type': 'one_to_one'
                }
            }]
        }]

        with pytest.raises(ForeignKeyError) as excinfo:
            [doc for doc in sync._sync(nodes, 'testdb')]
        msg = (
            'No foreign key relationship between '
            '"public.book" and "public.city"'
        )
        assert msg in str(
            excinfo.value
        )

    def test_missing_relationships(self, sync, data):
        """Relationships must be present between parent and child"""
        nodes = [{
            'table': 'book',
            'children': [{
                'table': 'publisher'
            }]
        }]

        with pytest.raises(RelationshipError) as excinfo:
            [doc for doc in sync._sync(nodes, 'testdb')]
        assert 'Relationship not present on "public.publisher"' in str(
            excinfo.value
        )

    def test_update_primary_key_non_concurrent(
        self, data, book_cls, publisher_cls, engine
    ):
        """
        Test sync updates primary_key and then sync in non-concurrent mode.
        """
        document = {
            'index': 'testdb',
            'nodes': [{
                'table': 'book',
                'columns': ['isbn', 'title'],
                'children': [{
                    'table': 'publisher',
                    'columns': ['id', 'name'],
                    'relationship': {
                        'variant': 'object',
                        'type': 'one_to_one'
                    }
                }]
            }]
        }
        sync = Sync(document)
        sync.sync()
        sync.es.refresh('testdb')

        docs = search(sync.es, 'testdb')

        assert docs == [
            {
                u'_meta': {'publisher': {'id': [1]}},
                u'isbn': u'abc',
                u'publisher': {'id': 1, 'name': 'Tiger publishing'},
                u'title': u'The Tiger Club'
            },
            {
                u'_meta': {'publisher': {'id': [2]}},
                u'isbn': u'def',
                u'publisher': {'id': 2, 'name': 'Lion publishing'},
                u'title': u'The Lion Club'
            },
            {
                u'_meta': {'publisher': {'id': [3]}},
                u'isbn': u'ghi',
                u'publisher': {'id': 3, 'name': 'Hop Bunny publishing'},
                u'title': u'The Rabbit Club'
            }
        ]
        session = sync.session

        try:
            session.execute(
                publisher_cls.__table__.insert().values(
                    id=99,
                    name='Rabbit publishers'
                )
            )
            session.execute(
                book_cls.__table__.update().where(
                    book_cls.__table__.c.publisher_id == 3
                ).values(publisher_id=99)
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

        sync.sync()
        sync.es.refresh('testdb')

        docs = search(sync.es, 'testdb')

        assert docs == [
            {
                u'_meta': {'publisher': {'id': [1]}},
                u'isbn': u'abc',
                u'publisher': {'id': 1, 'name': 'Tiger publishing'},
                u'title': u'The Tiger Club'
            },
            {
                u'_meta': {'publisher': {'id': [2]}},
                u'isbn': u'def',
                u'publisher': {'id': 2, 'name': 'Lion publishing'},
                u'title': u'The Lion Club'
            },
            {
                u'_meta': {'publisher': {'id': [99]}},
                u'isbn': u'ghi',
                u'publisher': {'id': 99, 'name': 'Rabbit publishers'},
                u'title': u'The Rabbit Club'
            }
        ]
        assert_resync_empty(
            sync,
            document.get('nodes', []),
            document.get('index'),
        )

    # TODO: Add another test like this and change
    # both primary key and non pkey column
    def test_update_primary_key_concurrent(
        self, data, book_cls, publisher_cls
    ):
        """Test sync updates primary_key and then sync in concurrent mode."""
        document = {
            'index': 'testdb',
            'nodes': [{
                'table': 'book',
                'columns': ['isbn', 'title'],
                'children': [{
                    'table': 'publisher',
                    'columns': ['id', 'name'],
                    'relationship': {
                        'variant': 'object',
                        'type': 'one_to_one'
                    }
                }]
            }]
        }
        sync = Sync(document)
        sync.sync()
        sync.es.refresh('testdb')

        docs = search(sync.es, 'testdb')

        assert docs == [
            {
                u'_meta': {'publisher': {'id': [1]}},
                u'isbn': u'abc',
                u'publisher': {'id': 1, 'name': 'Tiger publishing'},
                u'title': u'The Tiger Club'
            },
            {
                u'_meta': {'publisher': {'id': [2]}},
                u'isbn': u'def',
                u'publisher': {'id': 2, 'name': 'Lion publishing'},
                u'title': u'The Lion Club'
            },
            {
                u'_meta': {'publisher': {'id': [3]}},
                u'isbn': u'ghi',
                u'publisher': {'id': 3, 'name': 'Hop Bunny publishing'},
                u'title': u'The Rabbit Club'
            }
        ]

        session = sync.session

        def pull():
            txmin = sync.checkpoint
            txmax = sync.txid_current
            sync.logical_slot_changes(txmin=txmin, txmax=txmax)

        def poll_redis():
            return []

        def poll_db():
            try:
                session.execute(
                    publisher_cls.__table__.insert().values(
                        id=99,
                        name='Rabbit publishers'
                    )
                )
                session.execute(
                    book_cls.__table__.update().where(
                        book_cls.__table__.c.publisher_id == 3
                    ).values(publisher_id=99)
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

        with mock.patch('pgsync.sync.Sync.poll_redis', side_effect=poll_redis):
            with mock.patch('pgsync.sync.Sync.poll_db', side_effect=poll_db):
                with mock.patch('pgsync.sync.Sync.pull', side_effect=pull):
                    with mock.patch(
                        'pgsync.sync.Sync.truncate_slots',
                        side_effect=truncate_slots,
                    ):
                        sync.receive()
                        sync.es.refresh('testdb')

        docs = search(sync.es, 'testdb')

        assert docs == [
            {
                u'_meta': {'publisher': {'id': [1]}},
                u'isbn': u'abc',
                u'publisher': {'id': 1, 'name': 'Tiger publishing'},
                u'title': u'The Tiger Club'
            },
            {
                u'_meta': {'publisher': {'id': [2]}},
                u'isbn': u'def',
                u'publisher': {'id': 2, 'name': 'Lion publishing'},
                u'title': u'The Lion Club'
            },
            {
                u'_meta': {'publisher': {'id': [99]}},
                u'isbn': u'ghi',
                u'publisher': {'id': 99, 'name': 'Rabbit publishers'},
                u'title': u'The Rabbit Club'
            }
        ]
        assert_resync_empty(
            sync,
            document.get('nodes', []),
            document.get('index'),
        )

    def test_insert_non_concurrent(self, data, book_cls, publisher_cls):
        """Test sync insert and then sync in non-concurrent mode."""
        document = {
            'index': 'testdb',
            'nodes': [{
                'table': 'book',
                'columns': ['isbn', 'title'],
                'children': [{
                    'table': 'publisher',
                    'columns': ['id', 'name'],
                    'relationship': {
                        'variant': 'object',
                        'type': 'one_to_one'
                    }
                }]
            }]
        }
        sync = Sync(document)
        sync.sync()
        sync.es.refresh('testdb')

        session = sync.session

        docs = search(sync.es, 'testdb')
        assert docs == [
            {
                u'_meta': {'publisher': {'id': [1]}},
                u'isbn': u'abc',
                u'publisher': {'id': 1, 'name': 'Tiger publishing'},
                u'title': u'The Tiger Club'
            },
            {
                u'_meta': {'publisher': {'id': [2]}},
                u'isbn': u'def',
                u'publisher': {'id': 2, 'name': 'Lion publishing'},
                u'title': u'The Lion Club'
            },
            {
                u'_meta': {'publisher': {'id': [3]}},
                u'isbn': u'ghi',
                u'publisher': {'id': 3, 'name': 'Hop Bunny publishing'},
                u'title': u'The Rabbit Club'
            }
        ]

        try:
            session.execute(
                publisher_cls.__table__.insert().values(
                    id=99,
                    name='Rabbit publishers'
                )
            )
            session.execute(
                book_cls.__table__.insert().values(
                    isbn='xyz',
                    title='Encyclopedia',
                    publisher_id=99
                )
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

        sync.sync()
        sync.es.refresh('testdb')

        docs = search(sync.es, 'testdb')

        assert docs == [
            {
                u'_meta': {'publisher': {'id': [1]}},
                u'isbn': u'abc',
                u'publisher': {'id': 1, 'name': 'Tiger publishing'},
                u'title': u'The Tiger Club'
            },
            {
                u'_meta': {'publisher': {'id': [2]}},
                u'isbn': u'def',
                u'publisher': {'id': 2, 'name': 'Lion publishing'},
                u'title': u'The Lion Club'
            },
            {
                u'_meta': {'publisher': {'id': [3]}},
                u'isbn': u'ghi',
                u'publisher': {'id': 3, 'name': 'Hop Bunny publishing'},
                u'title': u'The Rabbit Club'
            },
            {
                u'_meta': {'publisher': {'id': [99]}},
                u'isbn': u'xyz',
                u'publisher': {'id': 99, 'name': 'Rabbit publishers'},
                u'title': u'Encyclopedia'
            }
        ]
        assert_resync_empty(
            sync,
            document.get('nodes', []),
            document.get('index'),
        )

    def test_update_non_primary_key_non_concurrent(
        self, data, book_cls, publisher_cls
    ):
        """Test sync update and then sync in non-concurrent mode."""
        document = {
            'index': 'testdb',
            'nodes': [{
                'table': 'book',
                'columns': ['isbn', 'title'],
                'children': [{
                    'table': 'publisher',
                    'columns': ['id', 'name'],
                    'relationship': {
                        'variant': 'object',
                        'type': 'one_to_one'
                    }
                }]
            }]
        }
        sync = Sync(document)
        sync.sync()
        sync.es.refresh('testdb')

        docs = search(sync.es, 'testdb')

        assert docs == [
            {
                u'_meta': {'publisher': {'id': [1]}},
                u'isbn': u'abc',
                u'publisher': {'id': 1, 'name': 'Tiger publishing'},
                u'title': u'The Tiger Club'
            },
            {
                u'_meta': {'publisher': {'id': [2]}},
                u'isbn': u'def',
                u'publisher': {'id': 2, 'name': 'Lion publishing'},
                u'title': u'The Lion Club'
            },
            {
                u'_meta': {'publisher': {'id': [3]}},
                u'isbn': u'ghi',
                u'publisher': {'id': 3, 'name': 'Hop Bunny publishing'},
                u'title': u'The Rabbit Club'
            }
        ]

        session = sync.session

        try:
            session.execute(
                publisher_cls.__table__.update().where(
                    publisher_cls.__table__.c.id == 3
                ).values(name='Rabbit publishers')
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

        sync.sync()
        sync.es.refresh('testdb')

        docs = search(sync.es, 'testdb')

        assert docs == [
            {
                u'_meta': {'publisher': {'id': [1]}},
                u'isbn': u'abc',
                u'publisher': {'id': 1, 'name': 'Tiger publishing'},
                u'title': u'The Tiger Club'
            },
            {
                u'_meta': {'publisher': {'id': [2]}},
                u'isbn': u'def',
                u'publisher': {'id': 2, 'name': 'Lion publishing'},
                u'title': u'The Lion Club'
            },
            {
                u'_meta': {'publisher': {'id': [3]}},
                u'isbn': u'ghi',
                u'publisher': {'id': 3, 'name': 'Rabbit publishers'},
                u'title': u'The Rabbit Club'
            }
        ]
        assert_resync_empty(
            sync,
            document.get('nodes', []),
            document.get('index'),
        )

    def test_update_non_primary_key_concurrent(
        self, data, book_cls, publisher_cls
    ):
        """Test sync update and then sync in concurrent mode."""
        document = {
            'index': 'testdb',
            'nodes': [{
                'table': 'book',
                'columns': ['isbn', 'title'],
                'children': [{
                    'table': 'publisher',
                    'columns': ['id', 'name'],
                    'relationship': {
                        'variant': 'object',
                        'type': 'one_to_one'
                    }
                }]
            }]
        }
        sync = Sync(document)
        sync.sync()
        sync.es.refresh('testdb')

        docs = search(sync.es, 'testdb')

        assert docs == [
            {
                u'_meta': {'publisher': {'id': [1]}},
                u'isbn': u'abc',
                u'publisher': {'id': 1, 'name': 'Tiger publishing'},
                u'title': u'The Tiger Club'
            },
            {
                u'_meta': {'publisher': {'id': [2]}},
                u'isbn': u'def',
                u'publisher': {'id': 2, 'name': 'Lion publishing'},
                u'title': u'The Lion Club'
            },
            {
                u'_meta': {'publisher': {'id': [3]}},
                u'isbn': u'ghi',
                u'publisher': {'id': 3, 'name': 'Hop Bunny publishing'},
                u'title': u'The Rabbit Club'
            }
        ]

        session = sync.session

        def pull():
            txmin = sync.checkpoint
            txmax = sync.txid_current
            sync.logical_slot_changes(txmin=txmin, txmax=txmax)

        def poll_redis():
            return []

        def poll_db():
            with subtransactions(session):
                session.execute(
                    publisher_cls.__table__.update().where(
                        publisher_cls.__table__.c.id == 3
                    ).values(name='Rabbit publishers')
                )
                session.commit()

        with mock.patch('pgsync.sync.Sync.poll_redis', side_effect=poll_redis):
            with mock.patch('pgsync.sync.Sync.poll_db', side_effect=poll_db):
                with mock.patch('pgsync.sync.Sync.pull', side_effect=pull):
                    with mock.patch(
                        'pgsync.sync.Sync.truncate_slots',
                        side_effect=truncate_slots,
                    ):
                        sync.receive()
                        sync.es.refresh('testdb')

        docs = search(sync.es, 'testdb')

        assert docs == [
            {
                u'_meta': {'publisher': {'id': [1]}},
                u'isbn': u'abc',
                u'publisher': {'id': 1, 'name': 'Tiger publishing'},
                u'title': u'The Tiger Club'
            },
            {
                u'_meta': {'publisher': {'id': [2]}},
                u'isbn': u'def',
                u'publisher': {'id': 2, 'name': 'Lion publishing'},
                u'title': u'The Lion Club'
            },
            {
                u'_meta': {'publisher': {'id': [3]}},
                u'isbn': u'ghi',
                u'publisher': {'id': 3, 'name': 'Rabbit publishers'},
                u'title': u'The Rabbit Club'
            }
        ]
        assert_resync_empty(
            sync,
            document.get('nodes', []),
            document.get('index'),
        )

    def test_delete_concurrent(self, data, book_cls, publisher_cls):
        """Test sync delete and then sync in concurrent mode."""
        document = {
            'index': 'testdb',
            'nodes': [{
                'table': 'book',
                'columns': ['isbn', 'title'],
                'children': [{
                    'table': 'publisher',
                    'columns': ['id', 'name'],
                    'relationship': {
                        'variant': 'object',
                        'type': 'one_to_one'
                    }
                }]
            }]
        }

        sync = Sync(document)
        sync.sync()
        sync.es.refresh('testdb')

        docs = search(sync.es, 'testdb')

        assert docs == [
            {
                u'_meta': {'publisher': {'id': [1]}},
                u'isbn': u'abc',
                u'publisher': {'id': 1, 'name': 'Tiger publishing'},
                u'title': u'The Tiger Club'
            },
            {
                u'_meta': {'publisher': {'id': [2]}},
                u'isbn': u'def',
                u'publisher': {'id': 2, 'name': 'Lion publishing'},
                u'title': u'The Lion Club'
            },
            {
                u'_meta': {'publisher': {'id': [3]}},
                u'isbn': u'ghi',
                u'publisher': {'id': 3, 'name': 'Hop Bunny publishing'},
                u'title': u'The Rabbit Club'
            }
        ]

        session = sync.session

        def pull():
            txmin = sync.checkpoint
            txmax = sync.txid_current
            sync.logical_slot_changes(txmin=txmin, txmax=txmax)

        def poll_redis():
            return []

        def poll_db():
            try:
                session.execute(
                    publisher_cls.__table__.insert().values(
                        id=99,
                        name='Rabbit publishers'
                    )
                )
                session.execute(
                    book_cls.__table__.update().where(
                        book_cls.__table__.c.publisher_id == 3
                    ).values(publisher_id=99)
                )
                session.execute(
                    publisher_cls.__table__.delete().where(
                        publisher_cls.__table__.c.id == 3
                    )
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

        with mock.patch('pgsync.sync.Sync.poll_redis', side_effect=poll_redis):
            with mock.patch('pgsync.sync.Sync.poll_db', side_effect=poll_db):
                with mock.patch('pgsync.sync.Sync.pull', side_effect=pull):
                    with mock.patch(
                        'pgsync.sync.Sync.truncate_slots',
                        side_effect=truncate_slots,
                    ):
                        sync.receive()
                        sync.es.refresh('testdb')

        docs = search(sync.es, 'testdb')

        assert docs == [
            {
                u'_meta': {'publisher': {'id': [1]}},
                u'isbn': u'abc',
                u'publisher': {'id': 1, 'name': 'Tiger publishing'},
                u'title': u'The Tiger Club'
            },
            {
                u'_meta': {'publisher': {'id': [2]}},
                u'isbn': u'def',
                u'publisher': {'id': 2, 'name': 'Lion publishing'},
                u'title': u'The Lion Club'
            },
            {
                u'_meta': {'publisher': {'id': [99]}},
                u'isbn': u'ghi',
                u'publisher': {'id': 99, 'name': 'Rabbit publishers'},
                u'title': u'The Rabbit Club'
            }
        ]
        assert_resync_empty(
            sync,
            document.get('nodes', []),
            document.get('index'),
        )
