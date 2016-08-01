class Policy:
    def __init__(self, id, title, area, period, department, is_public, writer, docs, budget, keyword):
        self.id = id
        self.title = title
        self.area = area
        self.period = period
        self.department = department
        self.is_public = is_public
        self.writer = writer
        self.docs = docs
        self.budget = budget
        self.keyword = keyword

    def insert_policy_info_to_DB(self, cursor):
        cursor.execute("INSERT OR REPLACE into policy (id, title, area, department, period, is_public, writer, budget, keyword) \
                       values(?,?,?,?,?,?,?,?,?);", (self.id, self.title, self.area, self.department, self.period, self.is_public, self.writer, self.budget, "") )