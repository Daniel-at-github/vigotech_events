fetch_meetup.py

## 1. Requirements

The system must meet the following functional and non-functional requirements:

### Functional Requirements
1.  **Multi-Group Extraction**: The script must be capable of processing multiple Meetup groups in a single execution. 
2.  **External Configuration**: The list of groups must be defined in an external configuration file named `meetup.json`.
3.  **Historical Retrieval**: The API query must retrieve **all** available events accesible without authentiaction (cookies, password, tokens, ...)
4.  **Data Transformation**:
    *   Dates in ISO 8601 format must be converted to Unix timestamps in milliseconds.
    *   Event URLs must be absolute (including the instance domain), not relative.
5.  **Standardized Output**:
    *   A JSON file must be generated for each processed group.
    *   The output filename must be deduced from the group's username (e.g., `crafters.json`).
    *   The output JSON schema must contain: `title`, `date`, and `url`.

### Non-Functional Requirements
1.  **Dependency Management**: The script must use `PEP 723` for dependency declaration, allowing direct execution via uv shebang.
2.  **Robustness**: The script must handle network errors (HTTP) and file read/write errors without crashing completely (where possible), reporting errors to `stderr`.
3.  **Language**: Source code and documentation must be maintained in English.
