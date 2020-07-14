/*
 * Use this SQL query to select patents between two dates.
 * Uncomment the lines to retrieve the company ID and the alternate name ID.
 */
SELECT
    p.patent_number as "Patent Number",
    p.patent_title as "Patent Title",
    -- p.company_id as "Company ID",
    c.name as "Company Name",
    -- p.company_alternate_name_id as "Alternate Name ID",
    an.name as "Company Name Listed on Patent",
    p.year,
    p.grant_date as "Grant Date",
    p.uspc_class as "USPC Classes"
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