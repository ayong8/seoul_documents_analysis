import sqlite3
import csv
import re

DATABASE_NAME = "./seoul_documents.db"

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
        with open("./data/edges_for_policy.txt", "w") as txt_file:
            for key, count in connection_counter_dict.items():
                print(key[0], key[1], count)
                txt_file.write(key[0] + "\t" + key[1] + "\t" + str(count) + "\n")

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
            # Filter by policy_id and date
            if (policy_id, month) not in edges_count_dict_by_policy_and_date.keys():
                edges_count_dict_by_policy_and_date[(policy_id, month)] = {}
            #print(edges_count_dict_by_policy_and_date[(policy_id, month)].keys())

            # If sender and receiver exist
            if sender and receivers and (receivers != 'No receiver'):
                # Iterate over all receivers if there are more than two receivers
                for receiver in receivers.split(","):
                    # There is same entry that was already inserted in the dictionary,
                    if (sender, receiver) in edges_count_dict_by_policy_and_date[(policy_id, month)].keys():
                        edges_count_dict_by_policy_and_date[(policy_id, month)][(sender, receiver)] += 1
                    else:
                        edges_count_dict_by_policy_and_date[(policy_id, month)][(sender, receiver)] = 1

        return edges_count_dict_by_policy_and_date
        '''
        #print("# of kinds of edges: " + str(len(connection_counter_dict)))
        with open("./data/edges_for_policy.txt", "w") as txt_file:
            for key1, edges in edges_count_dict_by_policy_and_date.items():
                policy_id = key1[0]
                month = key1[0]
                for key2, count in edges.items():
                    sender = key2[0]
                    receiver = key2[1]
                    txt_file.write(policy_id + "\t" + month + "\t" + \
                                   sender + "\t" + receiver + "\t" + str(count) + "\n")
        '''


    ### Get all senders and receivers from desirable period of months
    # input should be two digits of a month (e.g., 01, 03, 10)
    def get_senders_and_receivers_by_month(self, from_month, to_month):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        connections = []

        # Put together connections of all months
        for i in range(from_month, to_month+1):
            # 2d array expected (e.g., [ [sender1, receiver1-1,receiver1-2], [sender2, receiver2], ... ]
            if i < 10:
                connections_for_month = cursor.execute("SELECT idx, sender, receiver FROM documents_20150%d" % i)
            else:
                connections_for_month = cursor.execute("SELECT idx, sender, receiver FROM documents_2015%d" % i)
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

        rows = cursor.execute("SELECT sender, receiver, policy_id, doc_id, date FROM policy_documents")
        for connection in rows:
            id = connection[2] + "_" + str(connection[3])
            connection = Connection(id, connection[0], connection[1], \
                                    { 'policy_id': connection[2], 'doc_id': connection[3], 'date': connection[4] } )
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