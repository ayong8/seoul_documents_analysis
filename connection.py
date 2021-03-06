import sqlite3
import csv
import re
from datetime import datetime, timedelta
import pandas as pd

DATABASE_NAME = "../seoul_documents_analysis/seoul_documents.db"

class Connection:
    def __init__(self, doc_idx, sender, receiver, labels):
        self.doc_idx = doc_idx
        self.sender = sender
        self.receiver = receiver
        self.labels = labels

    # connections = set of Connection instances
    ### Count edges by senders and receivers and put them in the dictionary
    def count_connections(self, connections):
        connection_counter_dict = {}
        for connection in connections:
            sender = connection.sender
            receivers = connection.receiver
            # If sender and receiver exist
            if sender and receivers and (receivers != 'No receiver'):
                # Iterate over all receivers if there are more than two receivers
                for receiver in receivers.split(","):
                    # There is same entry that was already inserted in the dictionary,
                    if (sender, receiver) in connection_counter_dict.keys():
                        connection_counter_dict[(sender, receiver)] += 1
                    else:
                        connection_counter_dict[(sender, receiver)] = 1

        print("# of kinds of edges: " + str(len(connection_counter_dict)))

        return connection_counter_dict

    ### 정책별, 날짜별로 정제해서 dictionary로 추출
    ### Input: a list of Connection objects = [ Connection0, Connection1, ... ]
    ### Output: a dict that has keys of tuple (policy_id, date) and value
    '''
    e.g., { (2015-11, 201503) : { (sender1,receiver1): 3,
                                    (sender2,receiver2): 10 },
            (2015-10, 201503) : ... }
    '''
    def count_connections_by_policy_and_date(self, connections):
        edges_count_dict_by_policy_and_date = {}
        for connection in connections:
            sender = connection.sender
            receivers = connection.receiver
            policy_id = connection.labels["policy_id"]
            # 20XX-XX 부분만 추출해낸다 (월별 문서추출이므로)
            month = re.findall("[0-9]{4}-[0-9]{2}", connection.labels["date"])[0]
            policy_title = connection.labels["policy_title"]
            # Filter by policy_id and date
            if (policy_id, month, policy_title) not in edges_count_dict_by_policy_and_date.keys():
                edges_count_dict_by_policy_and_date[(policy_id, month, policy_title)] = {}
            #print(edges_count_dict_by_policy_and_date[(policy_id, month)].keys())

            # If sender and receiver exist
            if sender and receivers and (receivers != 'No receiver'):
                # Iterate over all receivers if there are more than two receivers
                for receiver in receivers.split(","):
                    # There is same entry that was already inserted in the dictionary,
                    if (sender, receiver) in edges_count_dict_by_policy_and_date[(policy_id, month, policy_title)].keys():
                        edges_count_dict_by_policy_and_date[(policy_id, month, policy_title)][(sender, receiver)] += 1
                    else:
                        edges_count_dict_by_policy_and_date[(policy_id, month, policy_title)][(sender, receiver)] = 1

        return edges_count_dict_by_policy_and_date

    def count_connections_by_policy(self, connections):
        edges_count_dict_by_policy_and_date = {}
        for connection in connections:
            sender = connection.sender
            receivers = connection.receiver
            policy_id = connection.labels["policy_id"]
            policy_dept = connection.labels["policy_dept"]
            policy_title = connection.labels["policy_title"]
            # Filter by policy_id and date
            if (policy_id, policy_dept, policy_title) not in edges_count_dict_by_policy_and_date.keys():
                edges_count_dict_by_policy_and_date[(policy_id, policy_dept, policy_title)] = {}

            # If sender and receiver exist
            if sender and receivers and (receivers != 'No receiver'):
                # Iterate over all receivers if there are more than two receivers
                for receiver in receivers.split(","):
                    # There is same entry that was already inserted in the dictionary,
                    if (sender, receiver) in edges_count_dict_by_policy_and_date[
                        (policy_id, policy_dept, policy_title)].keys():
                        edges_count_dict_by_policy_and_date[(policy_id, policy_dept, policy_title)][(sender, receiver)] += 1
                    else:
                        edges_count_dict_by_policy_and_date[(policy_id, policy_dept, policy_title)][(sender, receiver)] = 1

        return edges_count_dict_by_policy_and_date


    ### Get all senders and receivers from desirable period of months
    # input should be two digits of a month (e.g., 01, 03, 10)
    def get_senders_and_receivers_by_month(self, from_month, to_month):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        connections = []

        # Put together connections of all months
        # from_month = YYYYDD, to_month = YYYYDD

        from_date = datetime(int(from_month.split('-')[0]), int(from_month.split('-')[1]), 1)
        to_date = datetime(int(to_month.split('-')[0]), int(to_month.split('-')[1]), 2)
        date_dict = pd.DataFrame(pd.date_range(from_date, to_date, freq='M'))

        for idx, date in date_dict.items():
            months = [month.replace('-', '') for month in re.findall('[0-9]{4}-[0-9]{2}', str(date))]
            for current_month in months:
                connections_for_month = cursor.execute("SELECT idx, sender, receiver FROM documents_%s" % current_month)
            for connection in connections_for_month:
                connection = Connection(connection[0], connection[1], connection[2], "")
                connections.append(connection)

        conn.commit()
        conn.close()

        return connections

    def get_senders_and_receivers(self):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        connections = []

        rows = cursor.execute("SELECT pd.sender, pd.receiver, pd.policy_id, pd.doc_id, p.title, p.department, pd.date FROM policy_documents pd, policy p where pd.policy_id = p.id")
        for connection in rows:
            id = connection[2] + "_" + str(connection[3])
            connection = Connection(id, connection[0], connection[1], \
                                    { 'policy_id': connection[2], 'policy_dept': connection[5], \
                                      'doc_id': connection[3], 'date': connection[6], 'policy_title': connection[4] } )
            connections.append(connection)

        print("# of edges: " + str(len(connections)))
        conn.commit()
        conn.close()

        return connections

    def write_connections_to_csv(self, csv_file_name, connections):
        with open(csv_file_name, 'w') as csvfile:
            writer = csv.writer(csvfile, delimiter=',')
            for connection in connections:
                writer.writerow([connection.doc_idx, connection.sender, connection.receiver])