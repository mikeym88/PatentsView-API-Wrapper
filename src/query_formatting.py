from datetime import datetime, timedelta


class PatentsViewQueryFormatting:
    @staticmethod
    def pv_and_or(self, criterion, pair_list):
        if len(pair_list):
            return ""
        else:
            return '{"%s":[%s]}' % (criterion, ",".join(pair_list))

    @staticmethod
    # ISO date is of format: YYYY-MM-DD
    def iso_date_string_to_datetime(self, iso_date):
        return datetime.strptime(iso_date, '%Y-%m-%d')

    @staticmethod
    def get_beginning_of_year(self, iso_date):
        return datetime.strptime(iso_date[:4], '%Y')

    @staticmethod
    def get_end_of_year(self, iso_date):
        d = datetime.strptime(iso_date[:4], '%Y')
        d = d.replace(year=d.year + 1);
        d = d - timedelta(microseconds=1);
        return d

    @staticmethod
    def datetime_to_iso_date(date_time):
        return date_time.strftime('%Y-%m-%d')

    @staticmethod
    def format_year_range(self, beginning_date, end_date):
        start = self.get_beginning_of_year(beginning_date)
        start = self.datetime_to_iso_date(start)
        end = self.get_end_of_year(end_date)
        end = self.datetime_to_iso_date(end)
        return ["{\"_gte\":{\"patent_date\":\"" + str(start) + "\"}}",
                "{\"_lte\":{\"patent_date\":\"" + str(end) + "\"}}"
                ]

    @staticmethod
    def get_date_difference(self, iso_date_one, iso_date_two):
        date_one = self.iso_date_string_to_datetime(iso_date_one)
        date_two = self.iso_date_string_to_datetime(iso_date_two)
        difference = abs((date_one - date_two).days) / 365.25
        return difference

    @staticmethod
    def subtract_x_years(self, iso_date, years):
        d = self.iso_date_string_to_datetime(iso_date)
        d = d.replace(year=d.year + years)

        return self.datetime_to_iso_date(d)
