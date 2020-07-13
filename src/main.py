from query_formatting import PatentsViewQueryFormatting as PVQF
import requests
import json
from sqlalchemy import *
from sqlalchemy.orm import *
from sqlalchemy.ext.declarative import declarative_base
from os import path
import pandas
from urllib.parse import quote
import argparse
from datetime import datetime
import re
from typing import List


Base = declarative_base()
engine = create_engine('sqlite:///patentsview.db')


# Move Base classes to different file: https://stackoverflow.com/a/7479122/6288413
class AlternateName(Base):
    __tablename__ = "alternate_company_names"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    name = Column(String, nullable=False, unique=True)
    assignee_id = Column(String, nullable=True, unique=True)
    assignee_key_id = Column(String, nullable=True, unique=True)

    def __init__(self, company_id, name):
        self.company_id = company_id
        self.name = name.strip() if name else name


class Company(Base):
    __tablename__ = 'companies'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    assignee_id = Column(String, nullable=True, unique=True)
    assignee_key_id = Column(String, nullable=True, unique=True)

    def __init__(self, name):
        self.name = name

    @staticmethod
    def add_companies(companies):
        if type(companies) is str:
            companies = [companies]
        elif type(companies) is not list:
            raise ValueError("Companies must be either a list or a string.")
        for company in companies:
            if session.query(Company.name).filter_by(name=company).scalar() is None:
                c = Company(company)
                session.add(c)
        session.commit()


class Patent(Base):
    __tablename__ = 'patents'
    # the combination of Patent Number, Company Name ID, and Alternate Name ID should be unique
    # Source: https://stackoverflow.com/a/10061143/6288413
    __table_args__ = (UniqueConstraint('patent_number', 'company_id', 'company_alternate_name_id',
                                       name='_patents_uc'),)
    id = Column(Integer, primary_key=True)
    patent_number = Column(String)
    patent_title = Column(String)
    company_id = Column(Integer, ForeignKey('companies.id'))
    company_alternate_name_id = Column(Integer, ForeignKey('alternate_company_names.id'), nullable=True)
    year = Column(Integer)
    grant_date = Column(DateTime)
    uspc_class = Column(String)
    assignee_first_name = Column(String)
    assignee_last_name = Column(String)

    def __init__(self, patent_number, patent_title, company_id, year, grant_date, uspc_class,
                 assignee_first_name, assignee_last_name, company_alternate_name_id=None):
        self.patent_number = patent_number
        self.patent_title = patent_title
        self.company_id = company_id
        self.company_alternate_name_id = company_alternate_name_id
        self.year = year
        self.grant_date = datetime.strptime(grant_date, '%Y-%m-%d')
        self.uspc_class = uspc_class
        self.assignee_first_name = assignee_first_name
        self.assignee_last_name = assignee_last_name


class CitedPatent(Base):
    __tablename__ = 'cited_patents'
    __table_args__ = (
        # PrimaryKeyConstraint('citing_patent_number', 'cited_patent_number'),
        UniqueConstraint('citing_patent_number', 'cited_patent_number',
                         name='_citing_patents_uc'),
    )

    id = Column(Integer, primary_key=True)
    citing_patent_number = Column(String, ForeignKey('patents.patent_number'))
    cited_patent_number = Column(String, ForeignKey('patents.patent_number'))

    def __init__(self, patent_number, cited_patent_number):
        self.citing_patent_number = patent_number
        self.cited_patent_number = cited_patent_number


Base.metadata.create_all(engine)
Base.metadata.bind = engine
dbSession = sessionmaker(bind=engine)
session = dbSession()


# setting for searching for company name
# e.g.:     "_eq", "_begins", etc.
COMPANY_SEARCH_CRITERIA = '_eq'


# Application Variables
search_base_url = "https://dev.patentsview.org/"
patent_search_endpoint = search_base_url + "api/patents/query"
assignee_search_endpoint = search_base_url + "api/assignees/query"


def get_patent(patent_number, fields=None):
    patent_query = '{"patent_number":"%s"}' % patent_number
    fields = ('["patent_number","patent_title","patent_abstract","patent_date","patent_year",'
              '"patent_kind","patent_type","patent_processing_time","app_number","assignee_country","assignee_id",'
              '"assignee_organization","nber_category_title","nber_subcategory_title",'
              '"wipo_sector_title","wipo_field_title"]')
    return patentsview_get_request(patent_search_endpoint, patent_query, fields)


def get_all_company_patents(company, beginning_year=None, end_year=None, verbose=False):
    first_page = get_one_page_of_company_patents(company, beginning_year, end_year, verbose=verbose)
    patents = first_page["patents"]
    number_of_pages = 1
    if first_page["total_patent_count"] > first_page["count"]:
        number_of_pages = first_page["total_patent_count"] // 25
        if first_page["total_patent_count"] % 25:
            number_of_pages += 1
    for page_number in range(2, number_of_pages + 1):
        page_results = get_one_page_of_company_patents(company, beginning_year, end_year, page_number, verbose=verbose)
        if page_results["patents"]:
            patents += page_results["patents"]
    # TODO see if it is better to yield instead of to return
    return patents


def get_one_page_of_company_patents(company, beginning_year=None, end_year=None, page=1, perpage=25, verbose=False):
    print("Requesting PatentsView: %s, page %d" % (company, page))
    company_query = '{"%s":{"assignee_organization":"%s"}}' % (COMPANY_SEARCH_CRITERIA, company)
    date_range = None

    if beginning_year is not None and end_year is not None:
        date_range = PVQF.format_year_range(str(beginning_year) + "-01-01", str(end_year) + "-12-31")
    if date_range is not None:
        search_query = PVQF.pv_and_or("_and", [company_query] + date_range)
    else:
        search_query = company_query

    results_format = ('["patent_number","patent_date","patent_year","assignee_organization","app_date",'
                      '"patent_title","uspc_mainclass_id","assignee_first_name","assignee_last_name"]'
                      )
    sorting_format = '{"page":%d,"per_page":%d}' % (page, perpage)
    response_in_json = patentsview_get_request(patent_search_endpoint, search_query,
                                               results_format, sorting_format, verbose=verbose)
    response = json.loads(response_in_json)
    if verbose:
        print(response)
    return response


# https://stackoverflow.com/a/41837318/6288413
def patentsview_get_request(endpoint, query_param, format_param=None, options_param=None, sort_param=None,
                            verbose=False):
    if not endpoint:
        raise ValueError("Endpoint is empty or None.")
    if not query_param:
        raise ValueError("query_param is empty or None.")

    # Use urllib.parse's quote to escape JSON strings. See:
    # - https://stackoverflow.com/a/45758514/6288413
    # - https://stackoverflow.com/a/18723973/6288413
    endpoint_query = endpoint + "?q=" + quote(re.sub("(\r?\n)", " ", query_param))
    if format_param is not None:
        endpoint_query = endpoint_query + "&f=" + quote(format_param)
    if options_param is not None:
        endpoint_query = endpoint_query + "&o=" + quote(options_param)
    if sort_param is not None:
        endpoint_query = endpoint_query + "&so=" + quote(sort_param)
    if verbose:
        print(endpoint_query)
    r = requests.get(endpoint_query)
    if r.status_code != requests.codes.ok:
        raise Exception("Status code: %s\r\n%s" % (r.status_code, r.text))
    return r.text


def insert_alternate_names(primary_id, alternate_names, commit_after_insert=True):
    if type(primary_id) != int:
        raise ValueError("Primary id must be an integer.")
    if type(alternate_names) != list:
        raise ValueError("alternate_names must be a list.")

    company_id = session.query(Company.id).filter_by(id=primary_id).scalar()
    if company_id is None:
        raise Exception("Id does not exist")
    else:
        for alt_name in alternate_names:
            alt_name = alt_name.strip()
            if session.query(AlternateName.name).filter_by(name=alt_name).scalar() is None:
                print("Inserting alternate name: %s" % alt_name)
                session.add(AlternateName(primary_id, alt_name))

        # If there are lots of consecutive being made, committing after each addition would slow the program down
        # Set commit_after_insert to False and commit after all the insertions have been made
        if commit_after_insert:
            session.commit()


def insert_names(file_path):
    file_path = path.normpath(file_path)
    if not path.exists(file_path):
        raise ValueError("Not a valid path %s" % file_path)
    if file_path[-4:] == "xlsx":
        df = pandas.read_excel(file_path, header=1)
        Company.add_companies(df["Name 1"].to_list())
        for _, row in df.iterrows():
            index = df.columns.get_loc("Name 1")
            primary_name = row[index]
            primary_id = session.query(Company.id).filter_by(name=primary_name).scalar()
            alternate_names = [name for name in row[index+1:] if type(name) == str]
            insert_alternate_names(primary_id, alternate_names, False)
        session.commit()


def get_company_primary_id(name):
    company_id = session.query(Company.id).filter_by(name=name).scalar()
    if company_id:
        return company_id
    company_id = session.query(AlternateName.company_id).filter_by(name=name).scalar()
    if company_id:
        return company_id
    return None


def add_cited_patents(patents_list, limit=25, verbose=False):
    results_format = '["patent_number","cited_patent_number"]'
    q_list = ['"%s"' % patent_number for patent_number in patents_list]
    q_str = '{"patent_number":[%s]}' % ",".join(q_list)

    # PatentsView only accepts GET requests; the endpoints for GET requests have a max length of 2000 characters.
    # As such if the length of the endpoint exceeds the maximum allowed length, a '414 URI Too Long' error is returned.
    # (for an explanation see: https://stackoverflow.com/a/50018203/6288413)
    # To circumvent the issue, we have to break up the query into chunks
    patents = []
    endpoint_length = len(patent_search_endpoint) + len('&q=') + len(q_str) + len('&f=') + len(results_format)

    # The PatentsView API apparently only allows 25 patents to be looked up at a time, hence the need for limit
    # TODO: investigate why this is and if there is a way to change it
    if endpoint_length < 2000 and not limit:
        response = patentsview_get_request(patent_search_endpoint, q_str, results_format, verbose=verbose)
        results = json.loads(response)
        patents = results['patents']
    else:
        if limit and ((endpoint_length // 2000) < (endpoint_length // limit)):
            number_of_chunks = endpoint_length // limit + 1
        else:
            number_of_chunks = endpoint_length // 2000 + 1

        interval = max(len(q_list) // number_of_chunks, limit)
        num_intervals = range(len(q_list) // interval + 2)
        for i in num_intervals:
            start_index = i * interval
            end_index = (i + 1) * interval
            q_str = '{"patent_number":[%s]}' % ",".join(q_list[start_index:end_index])
            response = patentsview_get_request(patent_search_endpoint, q_str, results_format, verbose=verbose)
            results = json.loads(response)
            print(results)
            if results['patents']:
                patents += results['patents']

    # Patents that are already in the db
    cited_patents_in_db = [(x.citing_patent_number, x.cited_patent_number) for x in session.query(CitedPatent).all()]
    # Patents fetched
    cited_patent_objects = []
    # Add ALL cited patents to cited_patent_objects list
    for patent in patents:
        patent_number = patent["patent_number"]
        for cited_patent_number in patent["cited_patents"]:
            # Check if there are cited patents in the results and if they are already in the database
            cited_patent_number = cited_patent_number["cited_patent_number"]
            if cited_patent_number:
                cited_patent_objects.append((patent_number, cited_patent_number))

    # Remove the patents that already in the database
    cited_patent_objects = list(set(cited_patent_objects) - set(cited_patents_in_db))

    # Add the cited patents to the database
    for i in range(len(cited_patent_objects)):
        patent_number, cited_patent_number = cited_patent_objects[i]
        cited_patent_objects[i] = CitedPatent(patent_number, cited_patent_number)

    session.bulk_save_objects(cited_patent_objects)
    session.commit()
    # TODO: add patents not in Patents table


def add_patents(patents):
    patent_objects = []
    for p in patents:
        uspc_main_classes = ""

        # Concatenate the USPC Main class codes into the 'uspc_class' field
        # Example entry: '250; 376; 976; '
        for mainclass in p["uspcs"]:
            if mainclass["uspc_mainclass_id"]:
                uspc_main_classes += mainclass["uspc_mainclass_id"] + "; "
        if not uspc_main_classes:
            uspc_main_classes = None

        # A patent can have multiple assignees. If the assignee orgnization is in one of our tables (e.g. Companies,
        # AlternateNames), add an entry in the patents table for each name
        for assignee in p["assignees"]:
            # There is also an "assignee_key_id" field, which is currently unused
            assignee_organization = assignee["assignee_organization"]
            if assignee_organization:
                assignee_organization = assignee_organization.lower()
            assignee_first_name = assignee["assignee_first_name"]
            assignee_last_name = assignee["assignee_last_name"]

            # Check if the assignee is in one of the tables: companies, alternate_names
            assignee_id = session.query(Company.id).filter(
                func.lower(Company.name) == assignee_organization).first()
            assignee_alternate_id = None
            if assignee_id:
                assignee_id = assignee_id.id
            else:
                # TODO find a company/patent that satisfies this path so that this can be tested
                # TODO handle case where there is no assignee organization, just an individual's first & last name
                result = session.query(AlternateName.id, AlternateName.company_id)\
                    .filter(func.lower(AlternateName.name) == assignee_organization).first()
                if result:
                    assignee_id = result.company_id
                    assignee_alternate_id = result.id

            # If it is, add the record
            if assignee_id:
                p_obj = Patent(patent_number=p["patent_number"],
                               patent_title=p["patent_title"],
                               company_id=assignee_id,
                               year=p["patent_year"],
                               grant_date=p["patent_date"],
                               uspc_class=uspc_main_classes,
                               assignee_first_name=assignee_first_name,
                               assignee_last_name=assignee_last_name,
                               company_alternate_name_id=assignee_alternate_id
                               )

                # Check if the patent is already in the database; add it if it is not
                # TODO: change this so that the database is not read so frequently from disk
                if session.query(Patent)\
                        .filter_by(patent_number=p["patent_number"], company_id=assignee_id,
                                   company_alternate_name_id=assignee_alternate_id).first() is None:
                    patent_objects.append(p_obj)

    # Save the patents
    session.bulk_save_objects(patent_objects)
    session.commit()


def fetch_patents_for_all_companies_in_db(resume_from_company_id=None):
    if resume_from_company_id and type(resume_from_company_id) == int:
        company_query = session.query(Company.id).filter(Company.id >= resume_from_company_id).order_by(Company.id.asc()).all()
    else:
        company_query = session.query(Company.id).order_by(Company.id.asc()).all()

    # Insert patents
    for company_id in company_query:
        company_id = company_id[0]
        primary_names = session.query(Company.name).filter_by(id=company_id).all()
        alternate_names = session.query(AlternateName.name, AlternateName.id).filter_by(company_id=company_id).all()

        for org in primary_names:
            patents = get_all_company_patents(org[0], verbose=True)
            if patents:
                add_patents(patents)

        for org, alternate_name_id in alternate_names:
            patents = get_all_company_patents(org, verbose=True)
            if patents:
                add_patents(patents)


def fetch_all_cited_patent_numbers_for_all_patents_in_db():
    l = []
    for number in session.query(Patent.patent_number).all():
        l.append(number.patent_number)
    add_cited_patents(l, verbose=True)


def main():
    options = get_options()

    # Insert company names
    if options.path:
        try:
            insert_names(options.path[0])
        except Exception as e:
            print("Error Occurred: %s" % str(e))

    start_date = None
    if options.start_date:
        start_date = options.start_date[0]

    end_date = None
    if options.start_date:
        end_date = options.end_date[0]

    # TODO: implement functionality that uses the Start and End dates
    """
    fetch_patents_for_all_companies_in_db()
    fetch_all_cited_patent_numbers_for_all_patents_in_db()
    """
    fetch_all_cited_patent_numbers_for_all_patents_in_db()


def get_options():
    parser = argparse.ArgumentParser(description="A script that calls the PatentsView API.",
        # formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '-p', '--path', type=str, metavar="path", nargs=1,
        help="The path of the spreadsheet that has the list of names and alternate names."
    )

    parser.add_argument(
        '--start-date', type=int, metavar="start_date", nargs=1,
        help="The patents will have a grant date greater than or equal to the start date."
    )

    parser.add_argument(
        '--end-date', type=int, metavar="end_date", nargs=1,
        help="The patents will have a grant date less than or equal to the end date."
    )

    parser.add_argument(
        '-c', '--companies', type=str, metavar="companies", nargs='+',
        help="The companies whose patents you want to retrieve."
    )

    parser.add_argument(
        '--verbose', action="store_true",
        help="Enable verbose."
    )

    options = parser.parse_args()

    return options


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Program ended by user.")
