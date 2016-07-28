from Document import Document

class PolicyDocument(Document):
    def __init__(self, policy_id, doc_id, title, policy_title, date, sender, receiver, writer, url, url_for_html_file, url_for_hwp_file, hwp_file_name, is_public):
        super().__init__(doc_id, "", date, title, writer, "", sender, receiver, url, url_for_html_file, url_for_hwp_file, hwp_file_name)
        self.policy_id = policy_id
        self.policy_title = policy_title
        self.is_public = is_public

    def insert_relevant_doc_info_by_policy(self):
        pass
