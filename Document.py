import sqlite3
import csv

class Document:
    def __init__(self, doc_id, idx, date, title, writer, work_category, sender, receiver, url, url_for_html_file, url_for_hwp_file, hwp_file_name):
        self.doc_id = doc_id
        self.idx = idx
        self.date = date
        self.writer = writer
        self.work_category = work_category
        self.title = title
        self.sender = sender
        self.receiver = receiver
        self.url = url
        self.url_for_html_file = url_for_html_file
        self.url_for_hwp_file = url_for_hwp_file
        self.hwp_file_name = hwp_file_name

    def filter_and_insert_doc_info_to_DB(self, doc_info):

        # dictonary for every loop
        #print(doc_info)

        useless_work_cards = [u'예산집행및회계관리', u'복무관리', u'공무직관리', u'관용차량관리', u'인사관리', u'급여및수당관리', u'교육훈련관리']
        useless_title_words = [u'일지', u'휴가']

        # row_value[0]: package_id, 1: date, 2: work category, 3: title, 4: doc num
        # 5: writer, 6: preservation period, 7: 발신부서, 8: public or not, 9: copyright, 10: url
        ### 공개 = 1, 비공개 = 0, 부분공개 = 2
        # 문서가 비공개가 아닐 경우, 그리고 문서 url이 존재하는 문서들만 작업을 진행 (공개 혹은 부분공개일 경우...)
        if (doc_info[8] != 0) and (doc_info[9] != None):
            # 업무교류와 관계없는 과제카드들을 제외
            if doc_info[5] not in useless_work_cards:
                # 업무교류와 상관없는 제목을 가진 문서들을 제외
                if all(word not in doc_info[6] for word in useless_title_words):
                    self.idx = doc_info[0]
                    self.doc_id = str(doc_info[1])
                    self.date = doc_info[4]
                    self.title = doc_info[6]
                    self.writer = doc_info[7]
                    self.receiver = doc_info[2]
                    self.url = doc_info[9]
                    self.url_for_html_file = ''
                    self.url_for_hwp_file = ''
                    self.hwp_file_name = ''

    def extract_doc_info_from_web_for_policy(self):
        pass

    def count_documents_by_condition(self):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        result = cursor.execute("select count(*) from documents_201501 where (public = 1 or public = 2)")
        for i in result:
            print(i)

    def get_doc_info(self, from_month, to_month):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        documents = []

        # Put together connections of all months
        for i in range(from_month, to_month + 1):
            # 2d array expected (e.g., [ [sender1, receiver1-1,receiver1-2], [sender2, receiver2], ... ]
            if i < 10:
                documents_for_month = cursor.execute("SELECT idx, work_category, title, sender, receiver FROM documents_20150%d" % i)
            else:
                documents_for_month = cursor.execute("SELECT idx, work_category, title, sender, receiver FROM documents_2015%d" % i)

            for doc in documents_for_month:
                document = Document(doc[0], doc[1], doc[2], doc[3], doc[4])
                documents.append(document)

        conn.commit()
        conn.close()

        return documents

    def write_results_to_txt(self, txt_file_name, documents):
        with open(txt_file_name, 'w') as txtfile:
            for document in documents:
                if not document.receiver:
                    document.receiver = ""
                    print(str(document.idx) + "\t" + document.work_category + "\t" + document.title + "\t" + document.sender + "\t" + document. receiver)
                    txtfile.write(str(document.idx) + "\t" + document.work_category + "\t" + document.title + "\t" + document.sender + "\t" + document. receiver)

    def verify_dep_names_from_txt_file(self, txt_file_name, depts_list, towns_list):
        # If there is a match
        txt_file = open(txt_file_name, "r")
        filtered_output = {}
        total_count = 0

        for line in txt_file.readlines():
            # print line
            sender = line.split(" ")[0]
            receiver = line.split(" ")[1]
            count = line.split(" ")[2]
            # print(sender, receiver, count)

            if any(dept in receiver for dept in depts_list):
                for dept1 in depts_list:
                    if dept1 in receiver:
                        if '(' in receiver:
                            if all(town not in receiver for town in towns_list) and ('서울특별시' in receiver):
                                print(sender, dept1, count)
                                filtered_output[(sender, dept1)] = count
                                total_count += int(count)
                        else:
                            print(sender, dept1, count)
                            filtered_output[(sender, dept1)] = count
                            total_count += int(count)

        print("total count of filtered docs: " + str(total_count))
        return filtered_output