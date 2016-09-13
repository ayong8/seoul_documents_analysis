import networkx as nx
import matplotlib.pyplot as plt
import os
import matplotlib.font_manager as fm

PATH_TO_POLICY_GRAPHS_BY_MONTH = "./graphs_for_policy_by_month"
PATH_TO_POLICY_GRAPHS = "./graphs_for_policy"

class Network():
    def __init__(self, edges):
        self.edges = edges

    ### weight도 포함된 데이터를 보내야 되나

    def make_graph(self):
        edges = []
        for edge, count in self.edges.items():
            sender = edge[0].replace(" ", "")
            receiver = edge[1].replace(" ", "")
            # Transform dictionary into tuples with three elements (source, target, weight)
            # In case sender and receiver are the same, then take that edge out
            if sender != receiver:
                edges.append((sender, receiver, count))

        fp1 = fm.FontProperties(
            fname="./NotoSansCJKkr-Regular.otf")  # Free Font https://www.google.com/get/noto/pkgs/NotoSansKorean-windows.zip
        nx.set_fontproperties(fp1)

        G = nx.DiGraph()
        G.add_weighted_edges_from(edges)

        graph_pos = nx.spring_layout(G)
        weights = [weight / 2 for (source, target, weight) in edges]

        return (G, graph_pos, weights)


    def draw_policy_graph_by_month(self, policy_id, month, policy_title):
        print("Now: " + policy_id + ", " + month)
        # self.edges is a dictionary
        (G, graph_pos, weights) = self.make_graph()


        # we can now added edge thickness and edge color
        nx.draw_networkx_edges(G, graph_pos, width=weights, alpha=1, edge_color='black')
        nx.draw_networkx_nodes(G, graph_pos, node_size=100, node_color='red', alpha=1)
        nx.draw_networkx_labels(G, graph_pos, font_size=8)

        #plt.show()
        #f = plt.figure()
        policy_folder_name = policy_id + "_" + policy_title.replace(" ","").replace("/","").replace("'", "")
        os.system("mkdir './graphs_for_policy_by_month/%s'" % policy_folder_name)
        plt.axis('off')
        plt.savefig("./graphs_for_policy_by_month/%s/%s.png" % (policy_folder_name, month), bbox_inches="tight")
        plt.clf()
        G.clear()

    def make_whole_policy_graph(self, policy_id, policy_title):
        print("Now: " + policy_id + ", " + policy_title)

        (G, graph_pos, weights) = self.make_graph()

        # we can now added edge thickness and edge color
        nx.draw_networkx_edges(G, graph_pos, width=weights, alpha=1, edge_color='black')
        nx.draw_networkx_nodes(G, graph_pos, node_size=100, node_color='red', alpha=1)
        nx.draw_networkx_labels(G, graph_pos, font_size=8)

        policy_file_name = policy_id + "_" + policy_title.replace(" ", "").replace("/", "").replace("'", "")
        plt.axis('off')
        plt.savefig("./graphs_for_policy2/%s.png" % (policy_file_name), bbox_inches="tight")
        plt.clf()
        G.clear()

    def calculate_centralization_of_policy_graph(self, policy_id, policy_title):
        (G, graph_pos, weights) = self.make_graph()
        N = G.order()
        degrees = G.degree(weight='weight').values()
        print(degrees)
        max_degree = max(degrees)
        centralization = float((N * max_degree - sum(degrees))) / (N - 1) ** 2

        return centralization

    def calculate_centrality_of_policy_graph(self, policy_id, policy_dept, policy_title):
        (G, graph_pos, weights) = self.make_graph()
        #nodes_centrality_dict = nx.degree_centrality(G)
        nodes_centrality_dict = {}
        total_weight = 0

        for sender, receiver, edata in G.edges(data=True):
            total_weight += edata['weight']

        for sender, receiver, edata in G.edges(data=True):
            print(sender, receiver, edata['weight'])
            weight_sum_dept = 0
            if sender not in nodes_centrality_dict.keys():
                for sender1, receiver1, edata1 in G.edges(data=True):
                    if (sender == sender1) or (sender == receiver1):
                        weight_sum_dept += int(edata1['weight'])
                nodes_centrality_dict[sender] = weight_sum_dept / total_weight

            weight_sum_dept = 0
            if receiver not in nodes_centrality_dict.keys():
                for sender2, receiver2, edata2 in G.edges(data=True):
                    if (receiver == sender2) or (receiver == receiver2):
                        weight_sum_dept += int(edata2['weight'])
                nodes_centrality_dict[receiver] = weight_sum_dept / total_weight

        for node, centrality in nodes_centrality_dict.items():
            # e.g., '푸른도시국 산지방재과'면, '산지방재과'만 dept name으로 잡는다
            if len(policy_dept.split(" ")) > 1:
                policy_dept = policy_dept.split(" ")[1]
                print("split: " + policy_dept)
            if node == policy_dept:
                print(node + ": " + "{0:.2f}".format(centrality) + "*")
            #else:
            #    print(node + ": " + "{0:.2f}".format(centrality))

        return nodes_centrality_dict






