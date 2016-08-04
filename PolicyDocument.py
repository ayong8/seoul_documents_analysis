import sqlite3
import Document

DATABASE_NAME = './seoul_documents.db'

class PolicyDocument(Document.Document):
    def __init__(self, policy_id, doc_id, title, policy_title, date, sender, receiver, writer, url, url_for_html_file, url_for_hwp_file, hwp_file_name, is_public):
        super().__init__(doc_id, "", date, title, writer, "", sender, receiver, url, url_for_html_file, url_for_hwp_file, hwp_file_name)
        self.policy_id = policy_id
        self.policy_title = policy_title
        self.is_public = is_public

    def insert_relevant_doc_info_by_policy(self, cursor):
        cursor.execute('INSERT OR REPLACE INTO policy_documents (policy_id, doc_id, title, policy_title, sender, date, writer, \
            url, url_for_html_file, url_for_hwp_file, hwp_file_name, is_public) \
            values(?,?,?,?,?,?,?,?,?,?,?,?);', (self.policy_id, self.doc_id, self.title, self.policy_title, self.sender, \
                                                self.date, self.writer, self.url, self.url_for_html_file, \
                                                self.url_for_hwp_file, self.hwp_file_name, self.is_public))
        print("Inserted: " + self.policy_id + ", " + str(self.doc_id) + ", " + str(self.policy_title))

    def get_policy_urls_by_policy_id(self, cursor):
        #conn = sqlite3.connect(DATABASE_NAME)
        #cursor = conn.cursor()
        rows = [ row[0] for row in cursor.execute('select url from policy_documents').fetchall() ]

        return rows
