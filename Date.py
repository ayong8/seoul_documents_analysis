import re
from datetime import datetime
from datetime import date
from calendar import monthrange

START_YEAR = "2011"
START_MONTH = "01"
START_DAY = "01"
END_YEAR = "2016"
END_MONTH = "04"
END_DAY = "30"

class Date:
    def __init__(self, from_date, to_date):
        self.from_date = from_date
        self.to_date = to_date

    def format_year(self, year_str):
        if len(year_str) == 2:  # ex) 14
            year = '20' + year_str
        else:   # ex) 2014
            year = year_str

        return year

    def format_month(self, month_str):
        if len(month_str) == 1:  # ex) 1
            month = '0' + month_str
        else:  # ex) 01
            month = month_str

        return month

    def format_day(self, day_str):
        if len(day_str) == 1:  # ex) 1
            day = '0' + day_str
        else:  # ex) 01
            day = day_str

        return day



    def format_last_day_of_year(self, year_str):
        if int(year_str) < 2016:
            month_str = 12
            day_str = 31
        else:
            month_str = 4
            day_str = 30

        return (str(month_str), str(day_str))

    def format_last_day_of_month(self, year_str, month_str):

        return str(monthrange(int(year_str), int(month_str))[1])


    ### Input: [start date in any format] ~ [end date in any format]
    ### Output: tuple of (from_date, to_date)
    def format_date(self, date_str):
        date_from_to_tokens = date_str.split("~")
        # 숫자들만 다 잡아낸다
        date_tokens = re.findall("([0-9]+)", date_str)

        # 먼저 기본날짜로 초기화를 하고 시작
        from_year = START_YEAR
        from_month = START_MONTH
        from_day = START_DAY
        to_year = END_YEAR
        to_month = END_MONTH
        to_day = END_DAY

        # ~ 뒤에 to_date에 해당하는 문자열이 있다면
        if len(date_from_to_tokens) == 2:
            # 잡아낸 숫자토큰이 두개라면 (e.g., 2013년 ~ 2019년)
            if len(date_tokens) == 2:
                from_year = self.format_year(date_tokens[0])
                to_year = self.format_year(date_tokens[1])
                to_month = str(12)
                to_day = str(31)
            # 잡아낸 숫자토큰이 두개라면 (e.g., 2013년 3월 ~ 2019년 9월)
            if len(date_tokens) == 4:
                from_year = self.format_year(date_tokens[0])
                from_month = self.format_month(date_tokens[1])
                to_year = self.format_year(date_tokens[2])
                to_month = self.format_month(date_tokens[3])
                to_day = self.format_last_day_of_month(to_year, to_month)
            # 잡아낸 숫자토큰이 두개라면 (e.g., 2013.3.21 ~ 2019.2.5)
            if len(date_tokens) == 6:
                from_year = self.format_year(date_tokens[0])
                from_month = self.format_month(date_tokens[1])
                from_day = self.format_day(date_tokens[2])
                to_year = self.format_year(date_tokens[3])
                to_month = self.format_month(date_tokens[4])
                to_day = self.format_day(date_tokens[5])
        # ~ 뒤에 to_date에 해당하는 문자열이 없다면
        else:
            # 잡아낸 숫자토큰이 한개라면 (e.g., 2013년 ~ 지속)
            if len(date_tokens) == 1:
                from_year = self.format_year(date_tokens[0])
            # 잡아낸 숫자토큰이 두개라면 (e.g., 13.01 ~ )
            if len(date_tokens) == 2:
                from_year = self.format_year(date_tokens[0])
                from_month = self.format_month(date_tokens[1])
            # 잡아낸 숫자토큰이 두개라면 (e.g., 2014.2.1 ~ )
            if len(date_tokens) == 3:
                from_year = self.format_year(date_tokens[0])
                from_month = self.format_month(date_tokens[1])
                from_day = self.format_day(date_tokens[2])

        # 각 해당월의 마지막 달을 포맷


        from_date = from_year + "-" + from_month + "-" + from_day
        to_date = to_year + "-" + to_month + "-" + to_day

        return (from_date, to_date)

    # min_date : YYYY-MM-DD
    def set_range_of_from_date(self, from_date, min_date, max_date):
        from_date = date(int(from_date.split("-")[0]), int(from_date.split("-")[1]), int(from_date.split("-")[2]))
        min_date = date(int(min_date.split("-")[0]), int(min_date.split("-")[1]), int(min_date.split("-")[2]))
        max_date = date(int(max_date.split("-")[0]), int(max_date.split("-")[1]), int(max_date.split("-")[2]))

        if from_date <= min_date:
            from_date = min_date
        elif from_date > max_date:
            from_date = "Invalid"

        return str(from_date)

    def set_range_of_to_date(self, to_date, min_date, max_date):
        to_date = date(int(to_date.split("-")[0]), int(to_date.split("-")[1]), int(to_date.split("-")[2]))
        min_date = date(int(min_date.split("-")[0]), int(min_date.split("-")[1]), int(min_date.split("-")[2]))
        max_date = date(int(max_date.split("-")[0]), int(max_date.split("-")[1]), int(max_date.split("-")[2]))

        if to_date < min_date:
            to_date = "Invalid"
        elif to_date >= max_date:
            to_date = max_date

        return str(to_date)





    # ~ 뒤에 to_date에 해당하는 문자열이 없다면
