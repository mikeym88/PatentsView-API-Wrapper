from datetime import datetime, timedelta


class PatentsViewQueryFormatting:
    @staticmethod
    def pv_and_or(criterion, pair_list):
        if len(pair_list):
            return '{"%s":[%s]}' % (criterion, ",".join(pair_list))
        else:
            return ""

    @staticmethod
    # ISO date is of format: YYYY-MM-DD
    def iso_date_string_to_datetime(iso_date):
        return datetime.strptime(iso_date, '%Y-%m-%d')

    @staticmethod
    def get_beginning_of_year(iso_date):
        return datetime.strptime(iso_date[:4], '%Y')

    @staticmethod
    def get_end_of_year(iso_date):
        d = datetime.strptime(iso_date[:4], '%Y')
        d = d.replace(year=d.year + 1);
        d = d - timedelta(microseconds=1);
        return d

    @staticmethod
    def datetime_to_iso_date(date_time):
        return date_time.strftime('%Y-%m-%d')

    @staticmethod
    def format_year_range(beginning_date, end_date):
        if not beginning_date and not end_date:
            raise ValueError("Must provide a beginning date, an end_date, or both.")
        lst = []
        if beginning_date:
            start = PatentsViewQueryFormatting.get_beginning_of_year(beginning_date)
            start = PatentsViewQueryFormatting.datetime_to_iso_date(start)
            lst.append('{"_gte":{"patent_date":"%s"}}' % str(start))
        if end_date:
            end = PatentsViewQueryFormatting.get_end_of_year(end_date)
            end = PatentsViewQueryFormatting.datetime_to_iso_date(end)
            lst.append('{"_lte":{"patent_date":"%s"}}' % str(end))
        return lst

    @staticmethod
    def get_date_difference(iso_date_one, iso_date_two):
        date_one = PatentsViewQueryFormatting.iso_date_string_to_datetime(iso_date_one)
        date_two = PatentsViewQueryFormatting.iso_date_string_to_datetime(iso_date_two)
        difference = abs((date_one - date_two).days) / 365.25
        return difference

    @staticmethod
    def subtract_x_years(iso_date, years):
        d = PatentsViewQueryFormatting.iso_date_string_to_datetime(iso_date)
        d = d.replace(year=d.year + years)

        return PatentsViewQueryFormatting.datetime_to_iso_date(d)
