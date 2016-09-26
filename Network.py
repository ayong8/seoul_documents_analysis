import networkx as nx
import matplotlib.pyplot as plt
import os
import matplotlib.font_manager as fm
import collections

PATH_TO_POLICY_GRAPHS_BY_MONTH = "./graphs_for_policy_by_month"
PATH_TO_POLICY_GRAPHS = "./graphs_for_policy"

class Network():
    def __init__(self, edges):
        self.edges = edges

    ### weight도 포함된 데이터를 보내야 되나

    def make_graph(self):
        edges = []
        G = nx.DiGraph()

        for edge, count in self.edges.items():
            sender = edge[0].replace(" ", "")
            receiver = edge[1].replace(" ", "")
            # Transform dictionary into tuples with three elements (source, target, weight)
            # In case sender and receiver are the same, then take that edge out
            if sender != receiver:
                G.add_edge(sender, receiver, weight=count, weight2=1)

        fp1 = fm.FontProperties(
            fname="./NotoSansCJKkr-Regular.otf")  # Free Font https://www.google.com/get/noto/pkgs/NotoSansKorean-windows.zip
        nx.set_fontproperties(fp1)

        print(G.edges(data=True))

        graph_pos = nx.spectral_layout(G)
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
            if node == policy_dept:
                print(node + ": " + "{0:.2f}".format(centrality) + "*")
            #else:
            #    print(node + ": " + "{0:.2f}".format(centrality))

        return nodes_centrality_dict

    def calculate_closeness_centrality_of_policy_graph(self, policy_id, policy_dept, policy_title):
        (G, graph_pos, weights) = self.make_graph()
        closeness_centrality_dict = nx.closeness_centrality(G)

        for node, closeness in closeness_centrality_dict.items():
            #if node == policy_dept:
            print(node + ": " + "{0:.2f}".format(closeness))

        return closeness_centrality_dict

    def calculate_betweenness_centrality_of_policy_graph(self, policy_id, policy_dept, policy_title):
        (G, graph_pos, weights) = self.make_graph()
        betweenness_centrality_dict = nx.betweenness_centrality(G)

        for node, closeness in betweenness_centrality_dict.items():
            # if node == policy_dept:
            print(node + ": " + "{0:.2f}".format(closeness))

        return betweenness_centrality_dict

    # Returns: dictionary of { primary_dept_name: [ primary_dept_of_transitivity_coef, primary_dept_of_cycle_coef ] }
    def calculate_transitivity_cycle_coefficient_of_policy_graph(self, policy_id, policy_dept, policy_title):
        (G, graph_pos, weights) = self.make_graph()
        transitivity_count = 0
        cycle_count = 0
        transitivity_coefficient = 0
        cycle_coefficient = 0

        for start_node in G.nodes():
            num_of_neighbors_of_policy_dept = 0
            if start_node == policy_dept:
                for end_node in G.nodes():
                    try:
                        all_paths = nx.all_simple_paths(G, source=start_node, target=end_node)
                        #print(shortest_path)
                        #print(len(shortest_path))
                        for path in all_paths:
                            if (len(path) > 2):
                                # Denominator of score (all paths between start node and end node via an intermediate node)
                                num_of_neighbors_of_policy_dept += 1
                                # Count Transitivity
                                if G.has_edge(start_node, end_node):
                                    transitivity_count += 1
                                    print("Transitivity + 1")
                                    print(path)
                                if G.has_edge(end_node, start_node):
                                    cycle_count += 1
                                    print("Cycle + 1")
                                    print(path)
                    #if shortest_path doesn't exist
                    except nx.exception.NetworkXNoPath as e:
                        pass
                if num_of_neighbors_of_policy_dept != 0:
                    transitivity_coefficient = transitivity_count / num_of_neighbors_of_policy_dept
                    cycle_coefficient = cycle_count / num_of_neighbors_of_policy_dept
                print(policy_id + ": " + str(transitivity_coefficient) + ", " + str(cycle_coefficient))
            else:
                pass

        return { policy_dept: [transitivity_coefficient, cycle_coefficient]}







