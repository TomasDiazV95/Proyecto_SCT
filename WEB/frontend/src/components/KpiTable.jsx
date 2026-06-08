import React from "react";

function toNumber(value) {
  if (value === "" || value === null || value === undefined) {
    return null;
  }

  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function formatValue(value, type) {
  if (value === "") {
    return "";
  }

  if (value === null || value === undefined) {
    return "-";
  }

  if (type === "text") {
    return value;
  }

  if (type === "percent") {
    const n = toNumber(value);
    return n === null ? "-" : `${(n * 100).toFixed(1)}%`;
  }

  if (type === "decimal1") {
    const n = toNumber(value);
    return n === null ? "-" : n.toFixed(1);
  }

  const n = toNumber(value);
  return n === null
    ? "-"
    : new Intl.NumberFormat("es-CL", {
        maximumFractionDigits: 0,
      }).format(n);
}

function aggregateValue(rows, column) {
  if (column.key === "tramo") {
    return "TOTAL";
  }

  if (column.aggregate === "last") {
    return rows.length ? rows[rows.length - 1]?.[column.key] ?? "-" : "-";
  }

  const numericValues = rows
    .map((row) => toNumber(row[column.key]))
    .filter((value) => value !== null);

  if (!numericValues.length) {
    return "-";
  }

  if (column.aggregate === "avg" || column.type === "percent") {
    return numericValues.reduce((acc, value) => acc + value, 0) / numericValues.length;
  }

  return numericValues.reduce((acc, value) => acc + value, 0);
}

function complianceStyle(value, meta, mode = "meta") {
  const n = toNumber(value);
  const target = toNumber(meta);
  if (n === null) {
    return {};
  }

  const threshold = mode === "one" ? 1 : (target !== null ? target : 1);

  return {
    background: n >= threshold ? "#C6EFCE" : "#FFC7CE",
    color: n >= threshold ? "#006100" : "#9C0006",
    fontWeight: 700,
  };
}

export default function KpiTable({ columns, rows, totalRow: totalRowOverride, cumplimientoMode = "meta" }) {
  const totalRow = totalRowOverride || columns.reduce((acc, column) => {
    acc[column.key] = aggregateValue(rows, column);
    return acc;
  }, {});

  return (
    <div className="table-responsive">
      <table className="table table-bordered align-middle kpi-table mb-0">
        <thead className="table-light">
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className={column.align ? `text-${column.align}` : ""}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.tramo || row.label || index}-${index}`}>
              {columns.map((column) => {
                const value = row[column.key];
                const cellStyle = column.key === "cumplimiento" ? complianceStyle(value, row.meta, cumplimientoMode) : undefined;

                return (
                  <td
                    key={column.key}
                    className={column.align ? `text-${column.align}` : ""}
                    style={cellStyle}
                  >
                    {formatValue(value, column.type)}
                  </td>
                );
              })}
            </tr>
          ))}
          <tr className="kpi-total-row">
            {columns.map((column) => {
              const value = totalRow[column.key];
              const cellStyle = column.key === "cumplimiento" ? complianceStyle(value, totalRow.meta, cumplimientoMode) : undefined;

              return (
                <td key={`total-${column.key}`} className={column.align ? `text-${column.align}` : ""} style={cellStyle}>
                  {formatValue(value, column.type)}
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
