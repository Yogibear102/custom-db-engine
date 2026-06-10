import os
import shutil
import time
import traceback


class Table:

    def __init__(self, name: str, columns: list):
        self.name = name
        self.columns = columns
        self.n = len(columns)
        self.rows = {}
        self.max_records = 100000

    def insert(self, entry: dict):
        if len(self.rows) >= self.max_records:
            raise ValueError(f"table '{self.name}' is full (max {self.max_records})")

        entry_id = entry.get('id')
        if entry_id in self.rows:
            raise ValueError("same id already exists")

        if len(entry) != self.n:
            raise ValueError("entry must match the number of cols as the table")

        for key in entry:
            if key not in self.columns:
                raise ValueError(f"column {key} doesnt exist")
        for col in self.columns:
            if col not in entry:
                raise ValueError(f"missing column {col}")

        self.rows[entry_id] = entry

    def count(self):
        return len(self.rows)

    def select_all(self):
        return list(self.rows.values())

    def select_single_entry(self, entry_id):
        if entry_id in self.rows:
            return self.rows[entry_id]
        else:
            raise ValueError("given id doesnt exist")

    def delete_single_entry(self, entry_id):
        if entry_id in self.rows:
            del self.rows[entry_id]
        else:
            raise ValueError("given id doesnt exist")


class Database:

    def __init__(self, db_name: str, db_path: str):
        self.name = db_name
        self.path = db_path
        self.tables = {}

    def add_table(self, table: Table):
        if table.name in self.tables:
            raise ValueError("same table name already exists")
        self.tables[table.name] = table

    def drop_table(self, table_name: str):
        if table_name in self.tables:
            del self.tables[table_name]
        else:
            raise ValueError("given table name doesnt exist")

    def select_table(self, table_name: str):
        if table_name in self.tables:
            return self.tables[table_name]
        else:
            raise ValueError("given table name doesnt exist")

    def select_all_tables(self):
        return list(self.tables.keys())


class MiniDB:

    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.databases = {}
        self.crash_logs = []

    #databases──────────────────────────────────────────────────

    def create_db(self, db_name: str):
        if db_name in self.databases:
            raise ValueError("same database name already exists")
        os.makedirs(os.path.join(self.root_dir, db_name), exist_ok=True)
        self.databases[db_name] = Database(db_name, os.path.join(self.root_dir, db_name))
        print(f"database '{db_name}' created")

    def drop_db(self, db_name: str):
        if db_name in self.databases:
            shutil.rmtree(os.path.join(self.root_dir, db_name))
            del self.databases[db_name]
            print(f"database '{db_name}' dropped")
        else:
            raise ValueError("given database name doesnt exist")

    #tables─────────────────────────────────────────────────────

    def create_tb(self, db_name: str, table_name: str, columns: list):
        if db_name not in self.databases:
            raise ValueError("given database name doesnt exist")
        if "id" not in columns:
            raise ValueError("id column is required")
        table = Table(table_name, columns)
        self.databases[db_name].add_table(table)
        print(f"table '{table_name}' created")

    def drop_tb(self, db_name: str, table_name: str):
        if db_name not in self.databases:
            raise ValueError("given database name doesnt exist")
        self.databases[db_name].drop_table(table_name)
        path = self._table_path(db_name, table_name)
        if os.path.exists(path):
            os.remove(path)
        print(f"table '{table_name}' dropped")

    # crud ───────────────────────────────────────────────────────

    def insert(self, db_name: str, table_name: str, entry: dict):
        try:
            table = self._get_table(db_name, table_name)
            table.insert(entry)
            print(f"inserted record with id '{entry['id']}'")
        except Exception as e:
            self._log_crash("insert", e)
            raise

    def select_all(self, db_name: str, table_name: str):
        try:
            table = self._get_table(db_name, table_name)
            rows = table.select_all()
            self._print_table(table.columns, rows)
        except Exception as e:
            self._log_crash("select_all", e)
            raise

    def select_by_id(self, db_name: str, table_name: str, entry_id):
        try:
            table = self._get_table(db_name, table_name)
            row = table.select_single_entry(entry_id)
            self._print_table(table.columns, [row])
        except Exception as e:
            self._log_crash("select_by_id", e)
            raise

    def delete(self, db_name: str, table_name: str, entry_id):
        try:
            table = self._get_table(db_name, table_name)
            table.delete_single_entry(entry_id)
            print(f"deleted record with id '{entry_id}'")
        except Exception as e:
            self._log_crash("delete", e)
            raise

    def count(self, db_name: str, table_name: str):
        table = self._get_table(db_name, table_name)
        print(f"count: {table.count()}")

    # ── persistence ────────────────────────────────────────────────

    def save(self, db_name: str, table_name: str):
        try:
            table = self._get_table(db_name, table_name)
            path = self._table_path(db_name, table_name)
            with open(path, 'w') as f:
                f.write(",".join(table.columns) + "\n")
                for row in table.rows.values():
                    f.write(",".join(str(row[col]) for col in table.columns) + "\n")
            print(f"saved '{table_name}'")
        except Exception as e:
            self._log_crash("save", e)
            raise

    def save_all(self):
        for db_name, db in self.databases.items():
            for table_name in db.select_all_tables():
                self.save(db_name, table_name)

    def load_all(self):
        if not os.path.exists(self.root_dir):
            return
        for db_name in os.listdir(self.root_dir):
            db_path = os.path.join(self.root_dir, db_name)
            if not os.path.isdir(db_path):
                continue
            if db_name not in self.databases:
                self.databases[db_name] = Database(db_name, db_path)
            for fname in os.listdir(db_path):
                if fname.endswith(".csv"):
                    self._load_table(db_name, fname[:-4])

    def _load_table(self, db_name: str, table_name: str):
        path = self._table_path(db_name, table_name)
        if not os.path.exists(path):
            return
        with open(path, 'r') as f:
            lines = f.read().splitlines()
        if not lines:
            return
        columns = lines[0].split(",")
        if table_name not in self.databases[db_name].tables:
            self.create_tb(db_name, table_name, columns)
        table = self._get_table(db_name, table_name)
        for line in lines[1:]:
            if not line.strip():
                continue
            values = line.split(",")
            record = {}
            for col, val in zip(columns, values):
                try:
                    val = int(val)
                except ValueError:
                    try:
                        val = float(val)
                    except ValueError:
                        pass
                record[col] = val
            table.rows[record["id"]] = record

    # ── crash logs ─────────────────────────────────────────────────

    def get_crash_logs(self):
        if not self.crash_logs:
            print("no crash logs")
            return
        for log in self.crash_logs:
            print(f"[{log['time']}] {log['operation']}: {log['error']}")

    def _log_crash(self, operation: str, error: Exception):
        self.crash_logs.append({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "operation": operation,
            "error": str(error),
            "traceback": traceback.format_exc()
        })

    # ── helpers ────────────────────────────────────────────────────

    def _get_table(self, db_name: str, table_name: str) -> Table:
        if db_name not in self.databases:
            raise ValueError("given database name doesnt exist")
        return self.databases[db_name].select_table(table_name)

    def _table_path(self, db_name: str, table_name: str) -> str:
        return os.path.join(self.root_dir, db_name, f"{table_name}.csv")

    def _print_table(self, columns: list, rows: list):
        if not rows:
            print("no records found")
            return
        widths = {col: len(col) for col in columns}
        for row in rows:
            for col in columns:
                widths[col] = max(widths[col], len(str(row.get(col, ""))))
        header = "  ".join(col.ljust(widths[col]) for col in columns)
        print(header)
        print("-" * len(header))
        for row in rows:
            print("  ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns))


# ── cli ────────────────────────────────────────────────────────────────────────

def main():
    db = MiniDB("./minidb_data")
    db.load_all()
    current_db = None

    print("minidb v1.0 -- type 'help' to see commands")

    while True:
        try:
            prompt = "minidb> " if not current_db else f"minidb({current_db})> "
            cmd = input(prompt).strip()
            if not cmd:
                continue

            parts = cmd.split()
            op = parts[0].lower()

            if op == "help":
                print("""
  use <db>                              switch to a database
  create db <db>                        create a new database
  drop db <db>                          delete a database
  create table <table> <col1,col2,...>  create a table
  drop table <table>                    delete a table
  insert <table> <val1,val2,...>        insert a record
  select <table>                        show all records
  select <table> <id>                   show one record
  delete <table> <id>                   delete a record
  count <table>                         count records
  save <table>                          save table to disk
  save all                              save everything
  logs                                  show crash logs
  exit                                  save and quit
                """)

            elif op == "use":
                if parts[1] not in db.databases:
                    print(f"database '{parts[1]}' doesnt exist")
                else:
                    current_db = parts[1]
                    print(f"switched to '{current_db}'")

            elif op == "create" and parts[1].lower() == "db":
                db.create_db(parts[2])

            elif op == "drop" and parts[1].lower() == "db":
                db.drop_db(parts[2])
                if current_db == parts[2]:
                    current_db = None

            elif op == "create" and parts[1].lower() == "table":
                if not current_db:
                    print("pick a database first -- use <db>")
                    continue
                db.create_tb(current_db, parts[2], parts[3].split(","))

            elif op == "drop" and parts[1].lower() == "table":
                if not current_db:
                    print("pick a database first -- use <db>")
                    continue
                db.drop_tb(current_db, parts[2])

            elif op == "insert":
                if not current_db:
                    print("pick a database first -- use <db>")
                    continue
                table = db._get_table(current_db, parts[1])
                values = parts[2].split(",")
                record = {}
                for col, val in zip(table.columns, values):
                    try:
                        val = int(val)
                    except ValueError:
                        try:
                            val = float(val)
                        except ValueError:
                            pass
                    record[col] = val
                db.insert(current_db, parts[1], record)

            elif op == "select" and len(parts) == 2:
                if not current_db:
                    print("pick a database first -- use <db>")
                    continue
                db.select_all(current_db, parts[1])

            elif op == "select" and len(parts) == 3:
                if not current_db:
                    print("pick a database first -- use <db>")
                    continue
                try:
                    entry_id = int(parts[2])
                except ValueError:
                    entry_id = parts[2]
                db.select_by_id(current_db, parts[1], entry_id)

            elif op == "delete":
                if not current_db:
                    print("pick a database first -- use <db>")
                    continue
                try:
                    entry_id = int(parts[2])
                except ValueError:
                    entry_id = parts[2]
                db.delete(current_db, parts[1], entry_id)

            elif op == "count":
                if not current_db:
                    print("pick a database first -- use <db>")
                    continue
                db.count(current_db, parts[1])

            elif op == "save" and len(parts) == 2:
                if not current_db:
                    print("pick a database first -- use <db>")
                    continue
                db.save(current_db, parts[1])

            elif op == "save" and parts[1].lower() == "all":
                db.save_all()
                print("everything saved")

            elif op == "logs":
                db.get_crash_logs()

            elif op == "exit":
                db.save_all()
                print("bye")
                breakk

            else:
                print(f"unknown command -- type 'help' to see what's available")

        except Exception as e:
            print(f"error: {e}")


if __name__ == "__main__":
    main()