from query_formatting import PatentsViewQueryFormatting as PVQF
import requests
import json
from pprint import pprint
from sqlalchemy import *
from sqlalchemy.orm import *
from sqlalchemy.ext.declarative import declarative_base
from os import path
import pandas
import html
import argparse

Base = declarative_base()
engine = create_engine('sqlite:///patensview.db')


class AlternateName(Base):
    __tablename__ = "alternate_company_names"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    name = Column(String, nullable=False, unique=True)

    def __init__(self, company_id, name):
        self.company_id = company_id
        self.name = name.strip() if name else name


class Company(Base):
    __tablename__ = 'companies'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)

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
    # id/patent_id
    patent_number = Column(String, primary_key=True, autoincrement=False)
    patent_title = Column(String)
    company_id = Column(Integer, ForeignKey('companies.id'))
    company_alternate_name_id = Column(Integer, ForeignKey('alternate_company_names.id'), nullable=True)
    year = Column(String)
    grant_date = Column(String)
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
        self.grant_date = grant_date
        self.uspc_class = uspc_class
        self.assignee_first_name = assignee_first_name
        self.assignee_last_name = assignee_last_name


class CitedPatent(Base):
    __tablename__ = 'cited_patents'
    # id/patent_id
    citing_patent_number = Column(String, ForeignKey('patents.patent_number'), primary_key=True)
    cited_patent_number = Column(String, ForeignKey('patents.patent_number'))


Base.metadata.create_all(engine)
Base.metadata.bind = engine
dbSession = sessionmaker(bind=engine)
session = dbSession()



# setting for searching for company name
# e.g.:     "_eq", "_begins", etc.
COMPANY_SEARCH_CRITERIA = '_eq'


# Application Variables
search_base_url = "http://www.patentsview.org/"
patent_search_endpoint = search_base_url + "api/patents/query"
assignee_search_endpoint = search_base_url + "api/assignees/query"


def get_all_company_patents(company, beginning_year=None, end_year=None, verbose=False):
    first_page = get_one_page_of_company_patents(company, beginning_year, end_year, verbose=verbose)
    patents = first_page["patents"]
    number_of_pages = 1
    if first_page["total_patent_count"] > first_page["count"]:
        number_of_pages = first_page["total_patent_count"] // 25 + 1
    for page_number in range(2, number_of_pages + 1):
        page_results = get_one_page_of_company_patents(company, beginning_year, end_year, page_number, verbose=verbose)
        patents += page_results["patents"]
    # TODO see if it is better to yield instead of to return
    return patents


def get_one_page_of_company_patents(company, beginning_year=None, end_year=None, page=1, perpage=25, verbose=False):
    print("Requesting PatentsView: %s, page %d" % (company, page))
    company = html.escape(company).replace("&#x27;", "'")
    company_query = '{"%s":{"assignee_organization":"%s"} }' % (COMPANY_SEARCH_CRITERIA, company)
    date_range = None

    if beginning_year is not None and end_year is not None:
        date_range = PVQF.format_year_range(str(beginning_year) + "-01-01", str(end_year) + "-12-31")
    if date_range is not None:
        search_query = PVQF.pv_and_or("_and", company_query + date_range)
    else:
        search_query = company_query

    results_format = ('["patent_number","patent_date","patent_year","assignee_organization", "app_date",'
                      '"patent_title","uspc_mainclass_id","assignee_first_name","assignee_last_name"]'
                      )
    sorting_format = '{"page": %d,"per_page": %d}' % (page, perpage)
    response_in_json = patentsview_get_request(patent_search_endpoint, search_query,
                                               results_format, sorting_format, verbose=verbose)
    response = json.loads(response_in_json)
    if verbose:
        print(response)
    return response


# https://stackoverflow.com/questions/41686536/querying-patentsview-for-patents-of-multiple-assignee-organization
def patentsview_get_request(endpoint, query_param, format_param=None, options_param=None, sort_param=None,
                            verbose=False):
    if endpoint == "" and query_param == "":
        return False

    endpoint_query = endpoint + "?q=" + query_param
    if format_param is not None:
        endpoint_query = endpoint_query + "&f=" + format_param
    if options_param is not None:
        endpoint_query = endpoint_query + "&o=" + options_param
    if sort_param is not None:
        endpoint_query = endpoint_query + "&so=" + sort_param
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


def add_patents(patents, company_id, company_alternate_name_id, company_name):
    patent_objects = []
    for p in patents:
        uspc_main_classes = ""

        for mainclass in p["uspcs"]:
            if mainclass["uspc_mainclass_id"]:
                uspc_main_classes += mainclass["uspc_mainclass_id"] + "; "

        p_obj = Patent(patent_number=p["patent_number"],
                       patent_title=p["patent_title"],
                       company_id=company_id,
                       year=p["patent_year"],
                       grant_date=p["patent_date"],
                       uspc_class=uspc_main_classes,
                       # TODO: fix this.
                       assignee_first_name=None,    # p["assignees"]["assignee_first_name"],
                       assignee_last_name=None,      # p["assignees"]["assignee_last_name"],
                       company_alternate_name_id=company_alternate_name_id
                       )
        # TODO: handle case where a patent is assigned to more than 1 company
        if session.query(Patent.patent_number).filter_by(patent_number=p["patent_number"]).scalar() is None:
            patent_objects.append(p_obj)
    session.bulk_save_objects(patent_objects)
    session.commit()


def main():
    options = get_options()
    # Insert company names
    insert_names(options.path[0])

    max_company_id = session.query(func.max(Patent.company_id)).scalar()
    # Insert patents
    for company_id in session.query(Company.id).all():
        company_id = company_id[0]
        companies = session.query(Company.name).filter_by(id=company_id).all()
        companies += session.query(AlternateName.name).filter_by(company_id=company_id).all()

        for org in companies:
            patents = get_all_company_patents(org[0], verbose=True)
            if patents:
                add_patents(patents, company_id, org)


def get_options():
    parser = argparse.ArgumentParser(
        description="A script that calls the PatentsView API.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'path', type=str, metavar="path", nargs=1,
        help="The path of the spreadsheet that has the list of names and alternate names."
    )

    options = parser.parse_args()
    if not options.path:
        parser.error("Please submit a path.")
    return options


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Program ended by user.")
