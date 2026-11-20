// Formatos numericos compartidos. El Intl.NumberFormat se crea una vez (crearlo por celda es caro en tablas grandes).
const ENTERO_CL = new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 });

// Monto entero con separador de miles: 1234567 -> "1.234.567".
export function formatMoney(value) {
  return ENTERO_CL.format(Number(value || 0));
}

// Monto en millones: 1234567890 -> "1.235 M".
export function formatMoneyM(value) {
  return `${ENTERO_CL.format(Number(value || 0) / 1e6)} M`;
}
