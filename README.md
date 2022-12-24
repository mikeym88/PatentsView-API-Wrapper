# PatentsView API wrapper

This project is a wrapper for the PatentsView API.

* [PatentsView Glossary](https://patentsview.org/glossary) provides a description of the variables.

## Similar Projects

* The Patents Client project is a Python client for patents: [PyPI](https://pypi.org/project/patent-client/) | [GitHub](https://github.com/parkerhancock/patent_client) | [Docs](https://patent-client.readthedocs.io/en/latest/).

## Important Notes:

* An API key is required, one can be requested [here](https://patentsview.org/apis/keyrequest).
* There needs to be an environmental variable PATENTSVIEW_API_KEY set to the value of your API key.
* The endpoints of the new version of the API are at <https://search.patentsview.org>, they had last been at <https://api.patentsview.org/>.
* The API team produced a [Swagger UI page](https://search.patentsview.org/swagger-ui/) for the new version of the API. Your API key can be entered by pressing the Authorize button.
* The new version of the API does not seem to return USPC classifications, the code was switched to use CPC classifications.

## Remarks about the data

* Patent Numbers are alphanumeric (they can include letters)
* PatentsView only includes information about the patent at issue. It does not include changes to patent information after the patent has been issued.
    * This means that if the company changes name, it won't be reflected in the patent. Example: if "International Business Machines" renames itself to "IBM", patents issued to "International Business Machines" will still be issued to "International Business Machines" (and not "IBM").
    * As an example: `NETFLIX, INC.` has an `assignee_key_id` of `17594` and an `assignee_id` of `org_2lAuxOpAtNMvtTxhuLmX`; `NETFLIX.COM, INC.` on the other hand an `assignee_key_id` of `org_UNHkzir8tY7NlQrOJKT4` and an `assignee_id` of `363028`. (This of course assumes `NETFLIX, INC.` and `NETFLIX.COM, INC.` are the same company, which is highly probable).
    * The same applies for acquisitions. Example: Company A has patent *X*; once company B acquires company A, patent *X* would still show that it is assigned to company *A*.
    * Probably the same thing holds if a company acquires certain patents of another company.
* The patents can be assigned to organizations (as opposed to individuals). This is indicated by the 'assignees.assignee_organization' field returned by the API.
* The assignee organizations (i.e. companies) are distinguished by name. Each organization name is a 'separate' company.
    * This means that a patent can be assigned to "IBM", "IBM Inc.", "International Business Machines".
    * Different organization names have different `assignee_id`s and `assignee_key_id`s (see `NETFLIX` example above).

## Adding companies

Create an Microsoft Excel spreadsheet (`.xlsx` file) with the following structure:

<table>
    <thead>
        <tr>
            <th>Firm ID</th>
            <th>Firm Name</th>
            <th>Alternative names </th>
            <th></th>
            <th></th>
            <th></th>
            <th></th>
        </tr>
       <tr>
            <th>ID</th>
            <th>Name 1</th>
            <th>Name 2</th>
            <th>Name 3</th>
            <th>Name 4</th>
            <th>...</th>
            <th>Name X</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>ID2</td>
            <td>Company 2 Primary Name / Name 1</td>
            <td>Name 2</td>
            <td>Name 3</td>
            <td>Name 4</td>
            <td>...</td>
            <td>Name X</td>
        </tr>
        <tr>
            <td>ID1</td>
            <td>Company 1 Primary Name / Name 1</td>
            <td>Name 2</td>
            <td>Name 3</td>
            <td>Name 4</td>
            <td>...</td>
            <td>Name X</td>
        </tr>
    </tbody>
</table>


## Database Structure

Here is an Entity Relationship Diagram (ERD) of the database structure.

![Entity Relationship Diagram (ERD) of the database structure](images/patents_view_table.png)

## Using SQL to Select Patents

The `sql` folder has some SQL scripts that might come in handy. 
As an example, here is SQL query that selects patents between two dates:

```
SELECT
	p.patent_number as "Patent Number",
	p.patent_title as "Patent Title",
	-- p.company_id as "Company ID",
	c.name as "Company Name",
	-- p.company_alternate_name_id as "Alternate Name ID",
	an.name as "Company Name Listed on Patent",
	p.year,
	p.grant_date as "Grant Date",
	p.cpc_group_id as "CPC Subsections"
FROM 
	patents as p
JOIN 
	companies as c
ON
	p.company_id = c.id
LEFT JOIN 
	alternate_company_names as an
ON
	p.company_alternate_name_id = an.id
WHERE
	p.grant_date > DATE("2006-01-03") AND
	p.grant_date < DATE("2010-06-13");
```

## Software Applications

* [DbVisualizer](https://www.dbvis.com/) was used to generate the graphs
* [DB Browser for SQLite](https://sqlitebrowser.org/) was used to look at the data and execute SQL queries
