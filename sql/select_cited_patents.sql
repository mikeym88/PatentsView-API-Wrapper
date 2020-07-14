SELECT
	DISTINCT
	p.patent_number as "Citing Patent Number"
	,co.name as "Citing Company"
	,cp.cited_patent_number as "Cited Patent Number"
	,pp.patent_title as "Cited Patent Title"
	,pp.year as "Year"
	,pp.grant_date as "Grant Date"
	,pp.uspc_class as "USPC Class"
FROM
	patents as p
LEFT JOIN
	companies as co
ON
	co.id = p.company_id
JOIN
	cited_patents as cp
ON
	p.patent_number = cp.citing_patent_number
LEFT JOIN
	patents as pp
ON
	cp.cited_patent_number = pp.patent_number
-- Uncomment the following 2 lines if you to filter by patent_number (or something else of your choosing)
--WHERE
--	p.patent_number = "10001497"
ORDER BY 
	p.patent_number ASC