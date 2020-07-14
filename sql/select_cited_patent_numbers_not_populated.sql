/*
 * Use this script to find which cited patents need to be added to the Patents table.
 */
SELECT
    cited_patent_number
FROM
    cited_patents
WHERE
    cited_patent_number NOT IN (SELECT DISTINCT patent_number FROM patents);