##Problem:
- When user inputs tee, their intent is T-shirt but the db search tool cant tell , so we need a smater retrieval system. 
- Since we using sqlite for mvp purpose, (keeping it minimal), we implement the fts5 and fuzzyseach extension to normalise and diversify our seraches. 
- A more advanced stable stack at deployment is using postgress as our db and
We stack 3 measure toensure we capture everything in there; 
1): Normalization ; the usual .trim().lower() 
2): pg_trm - db level fuzzy search
    ```SELECT *, similarity(name, 'tshirt') AS score
FROM products
WHERE name % 'tshirt'
ORDER BY score DESC
LIMIT 5;```
This matches black t, tee, tshirt
3): Multi-field matching
- this ensures match existing across 3 categories, description, category and anything else;    ```SELECT *,
    similarity(name, 'tshirt') * 0.6 +
    similarity(description, 'tshirt') * 0.3 +
    similarity(category, 'tshirt') * 0.1 AS score
FROM products
ORDER BY score DESC
LIMIT 5;```
- now it can match even if we type polo.


| Stage  | Tool                     |
| ------ | ------------------------ |
| MVP    | SQLite + FTS             |
| Growth | PostgreSQL + pg_trgm     |
| Scale  | Vector search (pgvector) |
