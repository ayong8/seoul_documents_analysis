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
            # Transform dictionary into tuples with three elements (source, target, weight)
            print(edge[0], edge[1], count)
            edges.append((edge[0], edge[1], count))

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
        plt.savefig("./graphs_for_policy/%s.png" % (policy_file_name), bbox_inches="tight")
        plt.clf()
        G.clear()

    def calculate_centralization_of_policy_graph(self, policy_id, policy_title):
        (G, graph_pos, weights) = self.make_graph()
        N = G.order()
        indegrees = G.in_degree().values()
        max_in = max(indegrees)
        centralization = float((N * max_in - sum(indegrees))) / (N - 1) ** 2

        print(centralization)

    def calculate_centrality_of_policy_graph(self, policy_id, policy_title):
        (G, graph_pos, weights) = self.make_graph()
        nodes_centrality_dict = nx.degree_centrality(G)

        for node, centrality in nodes_centrality_dict.items():
            print(node + ": " + "{0:.2f}".format(centrality))





