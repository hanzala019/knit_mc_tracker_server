import pymysql
import os
from dotenv import load_dotenv

class Database:
    def __init__(self):
        load_dotenv()
        # print(os.getenv("HOST"))
        # print(os.getenv("USER"))
        # print(os.getenv("PASSWORD"))
        # print(os.getenv("DB"))
        try:
            # Establish connection
            self.connection = pymysql.connect(
                charset="utf8mb4",
                connect_timeout=10,
                host=os.getenv("HOST"),
                user=os.getenv("USER"),
                password=os.getenv("PASSWORD"),
                database=os.getenv("DB"),
                autocommit=True  # Enable auto-commit
                # cursorclass=pymysql.cursors.DictCursor
            )
            print("Connected to the database!")
        except pymysql.MySQLError as e:
            print(f"Error connecting to the database: {e}")

    def get_all(self, query, params=None):
        cursor = self.connection.cursor()
        try:
            if params:
                cursor.execute(query, params)  # Execute with parameters
            else:
                cursor.execute(query)  # Execute without parameters
            results = cursor.fetchall()
            cursor.close()
            return results
        except pymysql.MySQLError as e:
            print(f"Error fetching data: {e}")
            return None

    def get_one(self, query, params=None):
        cursor = self.connection.cursor()
        try:
            if params:
                cursor.execute(query, params)  # Execute with parameters
            else:
                cursor.execute(query)  # Execute without parameters
            result = cursor.fetchone()
            cursor.close()
            return result
        except pymysql.MySQLError as e:
            print(f"Error fetching data: {e}")
            return None

    def update(self, query, params=None):
        cursor = self.connection.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            self.connection.commit()
            return "Successfully updated."
        except pymysql.MySQLError as e:
            self.connection.rollback()  # Rollback if there's an error
            return f"Error while updating: {e}"

    def insert(self, query, params=None):
        cursor = self.connection.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            self.connection.commit()
            return "Successfully inserted."
        except pymysql.MySQLError as e:
            self.connection.rollback()  # Rollback if there's an error
            return f"Error while inserting: {e}"

    def delete(self, query, params=None):
        cursor = self.connection.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            self.connection.commit()
            return "Successfully deleted."
        except pymysql.MySQLError as e:
            self.connection.rollback()  # Rollback if there's an error
            return f"Error while deleting: {e}"

    def close(self):
        self.connection.close()
        print("Database connection closed.")




