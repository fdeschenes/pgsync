"""Trigger tests."""
import pytest

from pgsync.base import Base
from pgsync.trigger import CREATE_TRIGGER_TEMPLATE


@pytest.mark.usefixtures('table_creator')
class TestTrigger(object):
    """Trigger tests."""

    def test_trigger_template(self):
        expected = """
CREATE OR REPLACE FUNCTION table_notify() RETURNS TRIGGER AS $$
DECLARE
  channel TEXT;
  old_row JSON;
  new_row JSON;
  notification JSON;
  xmin BIGINT;

  primary_keys TEXT [] := (
      SELECT primary_keys
      FROM _pkey_view
      WHERE table_name = TG_TABLE_NAME::REGCLASS
  );
  foreign_keys TEXT [] := (
      SELECT foreign_keys
      FROM _fkey_view
      WHERE table_name = TG_TABLE_NAME
  );

BEGIN
    -- database is also the channel name.
    channel := CURRENT_DATABASE();

    IF TG_OP = 'DELETE' THEN
        old_row = ROW_TO_JSON(OLD);
        old_row := (
            SELECT JSONB_OBJECT_AGG(key, value)
            FROM JSON_EACH(old_row)
            WHERE key = ANY(primary_keys)
        );
        xmin := OLD.xmin;
    ELSE
        IF TG_OP <> 'TRUNCATE' THEN
            new_row = ROW_TO_JSON(NEW);
            new_row := (
                SELECT JSONB_OBJECT_AGG(key, value)
                FROM JSON_EACH(new_row)
                WHERE key = ANY(primary_keys || foreign_keys)
            );
            IF TG_OP = 'UPDATE' THEN
                old_row = ROW_TO_JSON(OLD);
                old_row := (
                    SELECT JSONB_OBJECT_AGG(key, value)
                    FROM JSON_EACH(old_row)
                    WHERE key = ANY(primary_keys || foreign_keys)
                );
            END IF;
            xmin := NEW.xmin;
        END IF;
    END IF;

    -- construct the notification as a JSON object.
    notification = JSON_BUILD_OBJECT(
        'xmin', xmin,
        'new', new_row,
        'old', old_row,
        'tg_op', TG_OP,
        'table', TG_TABLE_NAME,
        'schema', TG_TABLE_SCHEMA
    );

    -- Notify/Listen updates occur asynchronously,
    -- so this doesn't block the Postgres trigger procedure.
    PERFORM PG_NOTIFY(channel, notification::TEXT);

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
        assert CREATE_TRIGGER_TEMPLATE == expected

    def test_trigger_primary_key_function(self, connection):
        tables = {
            'book': ['isbn'],
            'publisher': ['id'],
            'book_language': ['id'],
            'author': ['id'],
            'language': ['id'],
            'subject': ['id'],
            'city': ['id'],
            'country': ['id'],
            'continent': ['id'],
        }
        pg_base = Base(connection.engine.url.database)
        for table_name, primary_keys in tables.items():
            query = (
                f"SELECT ARRAY_AGG(attname) "
                f"FROM pg_index "
                f"JOIN pg_attribute ON attrelid = indrelid AND attnum = ANY(indkey) "
                f"WHERE indrelid = '{table_name}'::regclass AND indisprimary"
            )
            rows = pg_base.query(query)[0]
            assert list(rows)[0] == primary_keys

    def test_trigger_foreign_key_function(self, connection):
        tables = {
            'book': ['publisher_id'],
            'publisher': None,
            'book_language': ['book_isbn', 'language_id'],
            'author': ['city_id'],
            'language': None,
            'subject': None,
            'city': ['country_id'],
            'country': ['continent_id'],
            'continent': None,
        }
        pg_base = Base(connection.engine.url.database)
        for table_name, foreign_keys in tables.items():
            query = (
                f"SELECT ARRAY_AGG(column_name::TEXT) FROM information_schema.key_column_usage "
                f"WHERE constraint_catalog=current_catalog AND "
                f"table_name='{table_name}' AND position_in_unique_constraint NOTNULL "
            )
            rows = pg_base.query(query)[0]
            assert rows[0] == foreign_keys
