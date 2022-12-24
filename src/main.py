from query_formatting import PatentsViewQueryFormatting as PVQF
import requests
import json
from sqlalchemy import *
from sqlalchemy.orm import *
from sqlalchemy.ext.declarative import declarative_base
import os
import pandas
from urllib.parse import quote
import argparse
from datetime import datetime
import re
from typing import List
import time

Base = declarative_base()
engine = create_engine('sqlite:///patentsview.db')
if 'PATENTSVIEW_API_KEY' not in os.environ:
    raise EnvironmentError("Failed because PATENTSVIEW_API_KEY is not set.")
api_key = os.getenv('PATENTSVIEW_API_KEY')
headers = {
    'X-Api-Key': api_key,
    'User-Agent': 'https://github.com/mikeym88/PatentsView-API-Wrapper',
    'accept': 'application/json',
    'Content-Type': 'application/json'
}

# Move Base classes to different file: https://stackoverflow.com/a/7479122/6288413
class AlternateName(Base):
    __tablename__ = "alternate_company_names"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id', name="fk1"))
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
    company_id = Column(Integer, ForeignKey('companies.id', name="fk2"), nullable=True)
    company_alternate_name_id = Column(Integer, ForeignKey('alternate_company_names.id', name="fk1"), nullable=True)
    year = Column(Integer)
    grant_date = Column(DateTime)
    cpc_group_id = Column(String)  # new version of the API does return USPCs
    assignee_first_name = Column(String)
    assignee_last_name = Column(String)

    def __init__(self, patent_number, patent_title, company_id, year, grant_date, cpc_group_id,
                 assignee_first_name, assignee_last_name, company_alternate_name_id=None):
        self.patent_number = patent_number
        self.patent_title = patent_title
        self.company_id = company_id
        self.company_alternate_name_id = company_alternate_name_id
        self.year = year
        self.grant_date = datetime.strptime(grant_date, '%Y-%m-%d')
        self.cpc_group_id = cpc_group_id
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
    citing_patent_number = Column(String, ForeignKey('patents.patent_number', name="fk2"))
    cited_patent_number = Column(String, ForeignKey('patents.patent_number', name="fk1"))

    def __init__(self, patent_number, cited_patent_number):
        self.citing_patent_number = patent_number
        self.cited_patent_number = cited_patent_number


Base.metadata.create_all(engine)
Base.metadata.bind = engine
dbSession = sessionmaker(bind=engine)
session = dbSession()

# setting for searching for company name
# e.g.:     "_eq", "_begins", etc.
COMPANY_SEARCH_CRITERIA = '_text_phrase'

# Application Variables
search_base_url = "https://search.patentsview.org/"
patent_search_endpoint = search_base_url + "api/v1/patent/"
assignee_search_endpoint = search_base_url + "api/v1/assignee/"
citation_search_endpoint =  search_base_url + "api/v1/patent/us_patent_citation/"

# The new version of the API now does return USPCs but we'll stay with cpcs
# After May 2015 the patent office stopped assigning uspcs to utility patents

import textwrap
import requests

# https://stackoverflow.com/a/61803546

def print_roundtrip(response, *args, **kwargs):
    format_headers = lambda d: '\n'.join(f'{k}: {v}' for k, v in d.items())
    print(textwrap.dedent('''
        ---------------- request ----------------
        {req.method} {req.url}
        {reqhdrs}

        {req.body}
        ---------------- response ----------------
        {res.status_code} {res.reason} {res.url}
        {reshdrs}

        {res.text}
    ''').format(
        req=response.request, 
        res=response, 
        reqhdrs=format_headers(response.request.headers), 
        reshdrs=format_headers(response.headers), 
    ))


def get_patent(patent_number, fields=None):
    patent_query = '{"patent_number":"%s"}' % patent_number
    fields = ('["patent_number","patent_title","patent_abstract","patent_date","patent_year",'
              '"cpc_current.cpc_subsection_id","cpc_current","patent_kind","patent_type",'
              '"assignees_at_grant.country","assignees_at_grant.assignee_id",'
              '"assignees_at_grant.organization"]')
    return patentsview_post_request(patent_search_endpoint, patent_query, fields)


def get_all_company_patents(company, beginning_year=None, end_year=None, verbose=False):
    first_page = get_one_page_of_company_patents(company, beginning_year, end_year, verbose=verbose)
    patents = first_page["patents"]
    number_of_pages = 1
    # API change, attribute was total_patent_count, now total_hits
    if first_page["total_hits"] > first_page["count"]:
        number_of_pages = first_page["total_hits"] // 25
        if first_page["total_hits"] % 25:
            number_of_pages += 1
    for page_number in range(2, number_of_pages + 1):
        page_results = get_one_page_of_company_patents(company, beginning_year, end_year, page_number, verbose=verbose)
        if page_results["patents"]:
            patents += page_results["patents"]
    # TODO see if it is better to yield instead of to return
    return patents


def get_one_page_of_company_patents(company, beginning_year=None, end_year=None, page=1, perpage=25, verbose=False):
    print("Requesting PatentsView: %s, page %d" % (company, page))
    company_query = '{"%s":{"assignees_at_grant.organization":"%s"}}' % (COMPANY_SEARCH_CRITERIA, company)
    date_range = None

    if beginning_year is not None and end_year is not None:
        date_range = PVQF.format_year_range(str(beginning_year) + "-01-01", str(end_year) + "-12-31")
    if date_range is not None:
        search_query = PVQF.pv_and_or("_and", [company_query] + date_range)
    else:
        search_query = company_query

    results_format = ('["patent_id","patent_date","patent_year","assignees.assignee_organization",'
                      '"cpc_current.cpc_group_id","cpc_current",'
                      '"patent_title","assignees.assignee_name_first","assignees.assignee_name_last"]'
                      )

    options = {}
    options["size"] = perpage  # the API defaults "size" to 100 rows if not specified and it can be up to 1000
                      
    # paging the newest way, we have to supply the previous pages' last element in the "after" parameter
    # it also means that there has to be a sort

    if after != "":
       options["after"] = after

    options_param =  json.dumps(options) 

    response = patentsview_post_request(patent_search_endpoint, search_query,
                                               results_format, options_param=options_param, verbose=verbose)
    if verbose:
        print(response)
    return response


# https://stackoverflow.com/a/41837318/6288413
# sort_param could be something like '[{"patent_date":"desc"},{"patent_id":"desc"}]'
def patentsview_post_request(endpoint, query_param, format_param=None, options_param=None, sort_param=None,
                            verbose=False):
    if not endpoint:
        raise ValueError("Endpoint is empty or None.")
    if not query_param:
        raise ValueError("query_param is empty or None.")

    # Use urllib.parse's quote to escape JSON strings. See:
    # - https://stackoverflow.com/a/45758514/6288413
    # - https://stackoverflow.com/a/18723973/6288413
    body = '{"q":' + re.sub("(\r?\n)", " ", query_param)

    # now for paging there needs to be sort field
    if sort_param is None:
       sort_param = '[{"' + get_default_sort_field(endpoint) + '":"desc"}]'

    if format_param is not None:
        body = body + ',"f":' + format_param
    if options_param is not None:
        body = body + ',"o":' + options_param
    if sort_param is not None:
        body = body + ',"s":' + sort_param

    body = body + '}'
    if verbose:
        print("url: {} body: {}".format(endpoint, body))

    r = requests.post(endpoint, headers=headers, data=body, hooks={'response': print_roundtrip})

    # the API now enforces throttling, we may be throttled if we send in more than 45 requests per minute
    if 429 == r.status_code:
        print("Throttled response from the api, retry in {} seconds".format(r.headers["Retry-After"]))
        time.sleep(int(r.headers["Retry-After"]))  # Number of seconds to wait before sending next request
        r = requests.post(endpoint, headers=headers, data=body, hooks={'response': print_roundtrip})  # retry query now

    if r.status_code != requests.codes.ok:
        if 400 <= r.status_code <= 499:
            if 403 == r.status_code:
                extra = 'Incorrect API Key'
            else:
                extra = r.headers["X-Status-Reason"]
        else:
            extra = ''

        raise Exception("Status code: %s\r\n%s\n" % (r.status_code, r.text, extra))

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
    file_path = os.path.normpath(file_path)
    if not os.path.exists(file_path):
        raise ValueError("Not a valid path %s" % file_path)
    if file_path[-4:] == "xlsx":
        df = pandas.read_excel(file_path, header=1)
        Company.add_companies(df["Name 1"].to_list())
        for _, row in df.iterrows():
            index = df.columns.get_loc("Name 1")
            primary_name = row[index]
            primary_id = session.query(Company.id).filter_by(name=primary_name).scalar()
            alternate_names = [name for name in row[index + 1:] if type(name) == str]
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


def fetch_all_cited_patent_numbers_for_all_patents_in_db(verbose=False):
    l = []
    for number in session.query(Patent.patent_number).distinct().all():
        l.append('"' + number.patent_number + '"')
    add_cited_patent_numbers(l, verbose=verbose)


def add_cited_patents(limit=REQUEST_SIZE, verbose=False):
    # This function populates the patents table with the missing information for the
    # patent numbers found in the cited_patents table
    # TODO refactor this function to accept a list of patents
    results_format = ('["patent_id","patent_date","patent_year",'
                      '"assignees.assignee_organization","cpc_current",'
                      '"patent_title","assignees.assignee_name_first","assignees.assignee_name_last"]'
                      )
    patents_in_db = session.query(Patent.patent_number)
    cited_patents_to_add = [x.cited_patent_number for x in session.query(CitedPatent.cited_patent_number)\
        .filter(~CitedPatent.cited_patent_number.in_(patents_in_db)).all()]
    for patents in fetch_patents_by_number(patent_search_endpoint, cited_patents_to_add, results_format, limit=limit, verbose=verbose):
        add_patents(patents)

def add_cited_patent_numbers(patents_list, limit=25, verbose=False):
    results_format = '["patent_number","cited_patent_number"]'
    # now we only get the citations from the citation endpoint
    cited_patents = fetch_patents_by_number(citation_search_endpoint, patents_list, results_format, limit=limit, verbose=verbose)

    # we have to call to get the details of the cited patents and then add them to the database
    # TODO refactor to make this a constant etc
    patents_format =  ('["patent_number","patent_date","patent_year",'
                      '"assignees_at_grant.organization","cpc_current",'
                      '"patent_title","assignees_at_grant.name_first","assignees_at_grant.name_last"]'
                      )

    for patents in fetch_patents_by_number(patent_search_endpoint, cited_patents, patents_format, limit=limit, verbose=verbose):
        add_cited_patent_numbers_to_db(patents)


def fetch_patents_by_number(search_endpoint, patents_list, results_format, limit=25, verbose=False):
    q_list = ['"%s"' % patent_number for patent_number in patents_list]
    q_str = '{"patent_number":[%s]}' % ",".join(q_list)

    # ** the api does accept POST requests
    # PatentsView only accepts GET requests; the endpoints for GET requests have a max length of 2000 characters.
    # As such if the length of the endpoint exceeds the maximum allowed length, a '414 URI Too Long' error is returned.
    # (for an explanation see: https://stackoverflow.com/a/50018203/6288413)
    # To circumvent the issue, we have to break up the query into chunks
    patents = []
    endpoint_length = len(patent_search_endpoint) + len('&q=') + len(q_str) + len('&f=') + len(results_format)

    # TODO: rework this
    # ** the options parameter needs to be set to retrieve move than 25 patents at a time
    # With the new API the default is increased to 100
    # ** options parameter "size": 1000  is max request size now, originally "per_page": 10000 

    # The PatentsView API apparently only allows 25 patents to be looked up at a time, hence the need for limit
    # TODO: investigate why this is and if there is a way to change it

    # we're calling either the patent endpoint or the new patent_citation endpoint
    # the nested entity we need will either be patents or patent_citations
    m = re.search(r'/([^/]*)/$', search_endpoint)
    return_entity = m.group(1) + "s"
    print("return entity: {}".format(return_entity))

    if endpoint_length < 2000:
        response = patentsview_post_request(search_endpoint, q_str, results_format, verbose=verbose)
        results = json.loads(response)
        # 'patents' if search_endpoint end in /patent/ 
        patents = results[return_entity]
        yield patents
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
            print("start index: {} end_index: {}".format(start_index, end_index))

            q_str = '{"patent_number":[%s]}' % ",".join(q_list[start_index:end_index])
            response = patentsview_post_request(search_endpoint, q_str, results_format, verbose=verbose)

            results = json.loads(response)
            if verbose:
                print(results)
            if results[return_entity]:
                patents += results[return_entity]

            # This is to potentially avoid a "Segmentation Fault (core dumped)" error

            # TODO change this to an implementation that is more programmatic
            if len(patents) >= 1000:
                yield patents
                patents = []
        yield patents


def add_cited_patent_numbers_to_db(citations: List) -> None:
    print("Adding cited patent numbers to db.")
    # Patents that are already in the db
    cited_patents_in_db = [(x.citing_patent_number, x.cited_patent_number) for x in
                           session.query(CitedPatent).all()]
    # Patents fetched
    cited_patent_objects = []
    # Add ALL cited patents to cited_patent_objects list
    # API change: now we get a list like these {"patent_id":"7767404","citation_patent_id":"7494776"}
    for citation in citations:
        patent_number = citation["patent_id"]
        # Check if there are cited patents in the results and if they are already in the database
        cited_patent_number = citation["citation_patent_id"]
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

def add_patents(patents):
    patent_objects = []
    for p in patents:
        cpc_group_id = ""  # now there is a cpc_group_id attribute, ex "cpc_group_id":"A47J43/0727"

        # Concatenate the CPC cpc_group_id codes into the 'cpc_group_id' field
        # Example entry: 'H01; Y02; '

        # a design patent wouldn't have cpcs and about 50% of plant patents don't have them
        if "cpc_current" in p:  
            for mainclass in p["cpc_current"]:
                if mainclass["cpc_group_id"]:
                    cpc_group_id += mainclass["cpc_group_id"] + "; "
            if not cpc_group_id:
                cpc_group_id = None
        else:
           cpc_group_id = None

        # A patent can have multiple assignees. If the assignee orgnization is in one of our tables (e.g. Companies,
        # AlternateNames), add an entry in the patents table for each name
        # It's also possible that a cited patent had no assignees
        if "assignees" in p:
            for assignee in p["assignees"]:
                # The new version of the API doesn't seem to have an "assignee_key_id" 
                # There is also an "assignee_key_id" field, which is currently unused
                assignee_organization = assignee["assignee_organization"]
                if assignee_organization:
                    assignee_organization = assignee_organization.lower()
                if "assignee_name_first" in assignee:
                    assignee_first_name = assignee["assignee_name_first"]
                else:
                   assignee_first_name = None
                if "assignee_name_last" in assignee:
                    assignee_last_name = assignee["assignee_name_last"]
                else:
                   assignee_last_name = None

                # Check if the assignee is in one of the tables: companies, alternate_names
                assignee_id = session.query(Company.id).filter(
                    func.lower(Company.name) == assignee_organization).first()
                assignee_alternate_id = None
                if assignee_id:
                    assignee_id = assignee_id.id
                else:
                    # TODO find a company/patent that satisfies this path so that this can be tested
                    # TODO handle case where there is no assignee organization, just an individual's first & last name
                    result = session.query(AlternateName.id, AlternateName.company_id) \
                        .filter(func.lower(AlternateName.name) == assignee_organization).first()
                    if result:
                        assignee_id = result.company_id
                        assignee_alternate_id = result.id

                p_obj = Patent(patent_number=p["patent_id"],
                           patent_title=p["patent_title"],
                           company_id=assignee_id,
                           year=p["patent_year"],
                           grant_date=p["patent_date"],
                           cpc_group_id=cpc_group_id,
                           assignee_first_name=assignee_first_name,
                           assignee_last_name=assignee_last_name,
                           company_alternate_name_id=assignee_alternate_id
                           )

                # Check if the patent is already in the database; add it if it is not
                # TODO: change this so that the database is not read so frequently from disk
                if session.query(Patent).filter_by(patent_number=p["patent_id"],
                                               company_id=assignee_id,
                                               company_alternate_name_id=assignee_alternate_id,
                                               assignee_first_name=assignee_first_name,
                                               assignee_last_name=assignee_last_name,).first() is None:
                    patent_objects.append(p_obj)

    # Save the patents
    session.bulk_save_objects(patent_objects)
    session.commit()


def fetch_patents_for_all_companies_in_db(resume_from_company_id=None, verbose=False):
    if resume_from_company_id and type(resume_from_company_id) == int:
        company_query = session.query(Company.id).filter(Company.id >= resume_from_company_id).order_by(
            Company.id.asc()).all()
    else:
        company_query = session.query(Company.id).order_by(Company.id.asc()).all()

    # Insert patents
    for company_id in company_query:
        company_id = company_id[0]
        primary_names = session.query(Company.name).filter_by(id=company_id).all()
        alternate_names = session.query(AlternateName.name, AlternateName.id).filter_by(company_id=company_id).all()

        for org in primary_names:
            patents = get_all_company_patents(org[0], verbose=verbose)
            if patents:
                add_patents(patents)

        for org, alternate_name_id in alternate_names:
            patents = get_all_company_patents(org, verbose=verbose)
            if patents:
                add_patents(patents)


def main():
    options = get_options()

    # Insert company names
    if options.path:
        try:
            insert_names(options.path)
        except Exception as e:
            print("Error Occurred: %s" % str(e))

    start_date = None
    if options.start_date:
        start_date = options.start_date[0]

    end_date = None
    if options.start_date:
        end_date = options.end_date[0]

    # TODO: implement functionality that uses the Start and End dates
    if options.fetch_patents_for_all_companies:
        company_id = options.resume_from_company_id
        if company_id:
            print("Fetching patents for all companies in the database, starting with company id %s." % company_id)
            fetch_patents_for_all_companies_in_db(company_id)
        else:
            print("Fetching patents for all companies in the database.")
            fetch_patents_for_all_companies_in_db()

    fetch_all_cited_patent_numbers_for_all_patents_in_db()
    add_cited_patents(verbose=True)


def get_options():
    parser = argparse.ArgumentParser(description="A script that calls the PatentsView API.",
                                     # formatter_class=argparse.RawDescriptionHelpFormatter
                                     )

    parser.add_argument(
        '-p', '--path', type=str, metavar="path",
        help="The path of the spreadsheet that has the list of names and alternate names."
    )

    parser.add_argument(
        '--fetch-patents-for-all-companies', action='store_true',
        help="If passed, fetch patents for all companies in the database."
    )

    parser.add_argument(
        '--fetch-cited-patent-numbers', action='store_true',
        help="If passed, fetch the patent numbers for all patents in the database"
    )

    parser.add_argument(
        '--fetch-all-cited-patents', action='store_true',
        help="If passed, fetch patents for all companies in the database."
    )

    parser.add_argument(
        '-r', '--resume-from-company-id', type=int,
        help="Resume fetching patent from this company id."
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

# most of the nested endpoints use {endpoint}_id these are the exceptions
use_patent_id = ["us_application_citation", "us_patent_citation", 
"rel_app_text", "foreign_citation"]

# Now for paging there has to be a sort field.  Here we'll provide defaults
# for each endpoint if one isn't specied
def get_default_sort_field(endpoint):

   # grab the last item on the url 
   fields = endpoint.split("/")
   ending = fields[-2]
   if ending in use_patent_id:
      return "patent_id"
   else:
      return ending + "_id"

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Program ended by user.")
