/**
 * SQL Navigator Frontend Logic
 * Bietet Tabellen-Inspektion (inkl. PK) und interaktive SQL-Ausführung.
 */

document.addEventListener("DOMContentLoaded", () => {
    loadDatabaseSchema();
    setupShortcuts();
});

// Tastenkombination Strg+Enter zum direkten Ausführen
function setupShortcuts() {
    const textarea = document.getElementById("sql-query");
    textarea.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
            e.preventDefault();
            executeCurrentQuery();
        }
    });
}

function clearEditor() {
    document.getElementById("sql-query").value = "";
    document.getElementById("sql-query").focus();
}

/**
 * Lädt die Tabellen- und Spaltenstrukturen beider Datenbanken.
 */
function loadDatabaseSchema() {
    const sidebar = document.getElementById("sidebar-schema");
    fetch("/api/sqlnav/schema")
        .then(res => res.json())
        .then(data => {
            renderSidebarSchema(data);
        })
        .catch(err => {
            console.error("Fehler beim Laden des Schemas:", err);
            sidebar.innerHTML = `<div style="color:#ff6b6b; font-size:0.85em; padding:10px;">Fehler beim Laden: ${err.message}</div>`;
        });
}

/**
 * Rendert die linke Navigationsleiste mit aufklappbaren Tabellen & Spalten (inkl. PK).
 */
function renderSidebarSchema(data) {
    const sidebar = document.getElementById("sidebar-schema");
    sidebar.innerHTML = "";

    const dbConfig = [
        { key: "garagedb", title: "garagedb (garage.db)", icon: "&#128663;" },
        { key: "wasserdb", title: "wasserdb (wasserverbrauch.db)", icon: "&#128167;" }
    ];

    dbConfig.forEach(db => {
        const groupDiv = document.createElement("div");
        groupDiv.className = "db-group";

        const titleDiv = document.createElement("div");
        titleDiv.className = "db-title";
        titleDiv.innerHTML = `${db.icon} <span>${db.title}</span>`;
        groupDiv.appendChild(titleDiv);

        const tables = data[db.key] || [];
        if (tables.length === 0) {
            const emptyP = document.createElement("p");
            emptyP.style.cssText = "color:#64748b; font-size:0.82em; margin: 4px 0 0 10px;";
            emptyP.textContent = "Keine Tabellen gefunden";
            groupDiv.appendChild(emptyP);
        } else {
            const tableList = document.createElement("ul");
            tableList.className = "table-list";

            tables.forEach(tbl => {
                const li = document.createElement("li");
                li.className = "table-item";

                // Tabellen-Header
                const header = document.createElement("div");
                header.className = "table-header";
                header.innerHTML = `
                    <div class="table-name-wrap">
                        <span class="toggle-icon">&#9654;</span>
                        <span>&#128196; ${tbl.name}</span>
                    </div>
                    <button class="quick-query-btn" title="SELECT * Abfrage in Editor einfügen" onclick="insertSelectQuery('${db.key}', '${tbl.name}', event)">SELECT</button>
                `;

                // Spaltenliste (aufklappbar)
                const colList = document.createElement("ul");
                colList.className = "columns-list";

                tbl.columns.forEach(col => {
                    const colLi = document.createElement("li");
                    colLi.className = "column-item";
                    
                    const pkBadge = col.pk ? '<span class="pk-badge">PK</span>' : '';
                    colLi.innerHTML = `
                        <span class="column-name">
                            ${pkBadge}
                            <span>${col.name}</span>
                        </span>
                        <span class="col-type">${col.type || 'ANY'}</span>
                    `;
                    colList.appendChild(colLi);
                });

                // Klick zum Auf- und Zuklappen
                header.addEventListener("click", (e) => {
                    if (e.target.classList.contains("quick-query-btn")) return;
                    const isOpen = colList.style.display === "block";
                    colList.style.display = isOpen ? "none" : "block";
                    const toggle = header.querySelector(".toggle-icon");
                    if (isOpen) {
                        toggle.classList.remove("open");
                    } else {
                        toggle.classList.add("open");
                    }
                });

                li.appendChild(header);
                li.appendChild(colList);
                tableList.appendChild(li);
            });

            groupDiv.appendChild(tableList);
        }

        sidebar.appendChild(groupDiv);
    });
}

/**
 * Hilfsfunktion: Setzt ein Standard-SELECT für die geklickte Tabelle in den Editor
 */
function insertSelectQuery(dbKey, tableName, event) {
    if (event) event.stopPropagation();
    document.getElementById("db-select").value = dbKey;
    const editor = document.getElementById("sql-query");
    editor.value = `SELECT * FROM ${tableName} LIMIT 50;`;
    editor.focus();
}

/**
 * Führt das SQL-Statement aus dem Textbereich auf der gewählten DB aus.
 */
function executeCurrentQuery() {
    const db = document.getElementById("db-select").value;
    const query = document.getElementById("sql-query").value.trim();
    const resultsWrap = document.getElementById("results-wrap");
    const statusText = document.getElementById("status-text");
    const resultMeta = document.getElementById("result-meta");
    const queryTime = document.getElementById("query-time");

    if (!query) {
        alert("Bitte gib ein SQL-Statement ein.");
        return;
    }

    resultsWrap.innerHTML = '<div style="color:#00d4ff; text-align:center; padding:40px 0;">Führe Abfrage aus...</div>';
    statusText.textContent = "Wird ausgeführt...";
    statusText.className = "";
    queryTime.textContent = "";

    const startTime = performance.now();

    fetch("/api/sqlnav/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ db: db, query: query })
    })
    .then(res => res.json())
    .then(data => {
        const duration = (performance.now() - startTime).toFixed(1);
        queryTime.textContent = `${duration} ms`;

        if (!data.success) {
            statusText.textContent = `Fehler: ${data.error}`;
            statusText.className = "status-error";
            resultMeta.textContent = "Fehler aufgetreten";
            resultsWrap.innerHTML = `
                <div style="padding: 20px; color: #ff6b6b; font-family: monospace; white-space: pre-wrap;">
                    <strong>[SQL-Fehler]</strong>\n${data.error}
                </div>
            `;
            return;
        }

        statusText.textContent = "Abfrage erfolgreich ausgeführt";
        statusText.className = "status-success";

        if (data.type === "select") {
            resultMeta.textContent = `${data.row_count} Zeile(n) geladen`;
            renderResultTable(data.columns, data.rows);
        } else {
            resultMeta.textContent = `${data.rows_affected} Zeile(n) betroffen`;
            resultsWrap.innerHTML = `
                <div style="padding: 25px; color: #00ff99; font-size: 0.95em;">
                    &#10004; Befehl erfolgreich ausgeführt. Betroffene Zeilen: <strong>${data.rows_affected}</strong>
                </div>
            `;
        }
    })
    .catch(err => {
        console.error("Netzwerkfehler:", err);
        statusText.textContent = "Verbindungsfehler";
        statusText.className = "status-error";
        resultsWrap.innerHTML = `<div style="padding:20px; color:#ff6b6b;">Netzwerk- oder Serverfehler: ${err.message}</div>`;
    });
}

/**
 * Rendert das Ergebnis als HTML-Tabelle
 */
function renderResultTable(columns, rows) {
    const resultsWrap = document.getElementById("results-wrap");

    if (!columns || columns.length === 0) {
        resultsWrap.innerHTML = '<div style="color:#888; text-align:center; padding:30px;">Keine Spalten zurückgegeben.</div>';
        return;
    }

    if (!rows || rows.length === 0) {
        resultsWrap.innerHTML = '<div style="color:#888; text-align:center; padding:30px;">Ergebnis ist leer (0 Zeilen).</div>';
        return;
    }

    let html = '<table style="margin-top:0; border-radius:0;"><thead><tr>';
    columns.forEach(col => {
        html += `<th style="position: sticky; top: 0; z-index: 2;">${col}</th>`;
    });
    html += '</tr></thead><tbody>';

    rows.forEach(row => {
        html += '<tr>';
        row.forEach(val => {
            const displayVal = (val === null) ? '<em style="color:#64748b;">NULL</em>' : escapeHtml(String(val));
            html += `<td>${displayVal}</td>`;
        });
        html += '</tr>';
    });

    html += '</tbody></table>';
    resultsWrap.innerHTML = html;
}

function escapeHtml(str) {
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
