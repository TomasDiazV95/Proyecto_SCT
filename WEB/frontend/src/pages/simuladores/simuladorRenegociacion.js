// Calculo del simulador de renegociacion (Panel de Simuladores). Solo calculo: sin React ni DOM.
// Mismo resultado que el simulador del banco: cuota fechada (descuenta cada cuota por sus dias desde
// la operacion), impuesto de timbres sobre el saldo y tabla de amortizacion con meses de gracia.
// El HTML de respaldo (Simulador Renegociacion Phoenix.html) lleva una copia de esta logica.

const DIA_MS = 24 * 60 * 60 * 1000;
// Itau Apoya: la parte que no va a cuotas se paga en un cuoton final a este plazo.
export const MESES_CUOTON = 24;
// Impuesto de timbres: 0,066% por mes de plazo, con tope de 0,8%.
const TIMBRE_MENSUAL = 0.00066;
const TIMBRE_TOPE = 0.008;

export const CAMPANAS = {
  estandar: {
    code: "estandar",
    titulo: "Otras campañas",
    detalle: "Crédito estándar · 100% en cuotas",
    icono: "bi-wallet2",
    pctCuotas: 100,
    pctBloqueado: false,
  },
  apoya: {
    code: "apoya",
    titulo: "Itaú Apoya",
    detalle: `75% en cuotas + cuotón final a ${MESES_CUOTON} meses`,
    icono: "bi-life-preserver",
    pctCuotas: 75,
    pctBloqueado: true,
  },
};

export const VALORES_INICIALES = {
  deuda: 0,
  abono: 0,
  pctCuotas: 100,
  tasa: 2,
  cuotas: 72,
  gracia: 2,
  fecha: "",
  seguro: 7.14,
  gastos: 0,
  notaria: 2000,
  holgura: 0,
};

export function sumarMeses(fecha, meses) {
  const resultado = new Date(fecha);
  const dia = resultado.getDate();
  resultado.setMonth(resultado.getMonth() + meses);
  // 31-ene + 1 mes = ultimo dia de febrero, no 3 de marzo.
  if (resultado.getDate() !== dia) {
    resultado.setDate(0);
  }
  return resultado;
}

function diasEntre(desde, hasta) {
  return Math.max(0, Math.ceil((hasta - desde) / DIA_MS));
}

export function fechaDesdeInput(valor) {
  if (!valor) {
    return null;
  }
  const [anio, mes, dia] = String(valor).split("-").map(Number);
  const fecha = new Date(anio, mes - 1, dia);
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}

export function fechaAInput(fecha) {
  const mes = String(fecha.getMonth() + 1).padStart(2, "0");
  const dia = String(fecha.getDate()).padStart(2, "0");
  return `${fecha.getFullYear()}-${mes}-${dia}`;
}

// Cuota constante que, descontada por los dias reales de cada vencimiento, paga el saldo.
function cuotaFechada(saldo, cuotas, tasa, operacion, primeraCuota) {
  if (tasa === 0) {
    return saldo / cuotas;
  }
  let descuento = 0;
  for (let i = 0; i < cuotas; i += 1) {
    const dias = diasEntre(operacion, sumarMeses(primeraCuota, i));
    descuento += 1 / Math.pow(1 + tasa, dias / 30);
  }
  return saldo / descuento;
}

function tablaAmortizacion(saldoInicial, cuota, cuotas, tasa, gracia, primeraCuota) {
  const filas = [];
  let saldo = saldoInicial;
  // En gracia no se paga: el interes se suma al saldo.
  for (let g = 1; g <= gracia; g += 1) {
    const inicio = saldo;
    const interes = inicio * tasa;
    saldo = inicio + interes;
    filas.push({ id: `G${g}`, gracia: true, fecha: null, inicio, cuota: null, capital: null, interes, saldo });
  }
  for (let n = 1; n <= cuotas; n += 1) {
    const inicio = saldo;
    const interes = inicio * tasa;
    let capital = cuota - interes;
    let pago = cuota;
    if (n === cuotas) {
      capital = inicio;
      pago = capital + interes;
    }
    saldo = Math.max(0, inicio - capital);
    filas.push({ id: String(n), gracia: false, fecha: sumarMeses(primeraCuota, n - 1), inicio, cuota: pago, capital, interes, saldo });
  }
  return filas;
}

// Cada error indica su campo, para marcarlo en el formulario.
function validar(v, operacion) {
  const errores = [];
  const err = (campo, mensaje) => errores.push({ campo, mensaje });
  if (!(v.deuda > 0)) err("deuda", "Ingresa un saldo de deuda mayor a cero.");
  if (v.abono < 0) err("abono", "El pie no puede ser negativo.");
  if (v.abono > v.deuda) err("abono", "El pie no puede ser mayor que la deuda.");
  if (v.pctCuotas < 0 || v.pctCuotas > 100) err("pctCuotas", "Debe estar entre 0% y 100%.");
  if (v.cuotas < 1) err("cuotas", "Debe ser al menos 1 cuota.");
  if (v.tasa < 0) err("tasa", "La tasa no puede ser negativa.");
  if (v.gracia < 0) err("gracia", "Los meses de gracia no pueden ser negativos.");
  if (v.seguro < 0) err("seguro", "No puede ser negativo.");
  if (v.gastos < 0) err("gastos", "No puede ser negativo.");
  if (v.notaria < 0) err("notaria", "No puede ser negativo.");
  if (v.holgura < 0) err("holgura", "No puede ser negativa.");
  if (!operacion) err("fecha", "Ingresa una fecha de operación válida.");
  return errores;
}

function num(valor) {
  const n = Number(valor);
  return Number.isFinite(n) ? n : 0;
}

// valores: { deuda, abono, pctCuotas, tasa (% mensual), cuotas, gracia, fecha (YYYY-MM-DD),
//            seguro (%), gastos (%), notaria ($), holgura ($) }
export function simular(valores) {
  const v = {
    deuda: num(valores.deuda),
    abono: num(valores.abono),
    pctCuotas: num(valores.pctCuotas),
    tasa: num(valores.tasa),
    cuotas: Math.floor(num(valores.cuotas)),
    gracia: Math.floor(num(valores.gracia)),
    seguro: num(valores.seguro),
    gastos: num(valores.gastos),
    notaria: num(valores.notaria),
    holgura: num(valores.holgura),
  };
  const operacion = fechaDesdeInput(valores.fecha);
  const errores = validar(v, operacion);
  if (errores.length) {
    return {
      ok: false,
      errores: errores.map((e) => e.mensaje),
      // Primer error de cada campo.
      erroresCampo: Object.fromEntries([...errores].reverse().map((e) => [e.campo, e.mensaje])),
    };
  }

  const tasa = v.tasa / 100;
  const base = Math.max(0, v.deuda - v.abono);
  const enCuotas = base * (v.pctCuotas / 100);
  const aCuoton = base - enCuotas;
  const cuoton = aCuoton * Math.pow(1 + tasa, MESES_CUOTON);
  const seguro = enCuotas * (v.seguro / 100);
  const gastos = enCuotas * (v.gastos / 100);

  const primeraCuota = sumarMeses(operacion, Math.max(1, v.gracia));
  const diasPrimeraCuota = diasEntre(operacion, primeraCuota);
  const ultimaCuota = sumarMeses(primeraCuota, v.cuotas - 1);
  const diasPlazo = Math.max(diasPrimeraCuota, diasEntre(operacion, ultimaCuota));
  const mesesPlazo = Math.max(1, Math.ceil(diasPlazo / 30));
  const tasaTimbre = Math.min(TIMBRE_TOPE, TIMBRE_MENSUAL * mesesPlazo);

  const antesImpuesto = enCuotas + seguro + gastos + v.notaria;
  const impuesto = tasaTimbre === 0 ? 0 : (antesImpuesto * tasaTimbre) / (1 - tasaTimbre);
  const saldoFinanciar = antesImpuesto + impuesto;

  const cuotaBanco = cuotaFechada(saldoFinanciar, v.cuotas, tasa, operacion, primeraCuota);
  // Cuota que se informa al cliente: con holgura y redondeada a la centena hacia arriba.
  const cuota = Math.ceil((cuotaBanco + v.holgura) / 100) * 100;
  const costoTotal = (cuotaBanco + v.holgura) * v.cuotas;
  const intereses = Math.max(0, costoTotal - saldoFinanciar);

  return {
    ok: true,
    errores: [],
    erroresCampo: {},
    cuota,
    cuotaBanco,
    cuoton,
    aCuoton,
    enCuotas,
    seguro,
    gastos,
    notaria: v.notaria,
    impuesto,
    holgura: v.holgura,
    saldoFinanciar,
    costoTotal,
    intereses,
    cuotas: v.cuotas,
    gracia: v.gracia,
    tasa: v.tasa,
    operacion,
    primeraCuota,
    diasPrimeraCuota,
    ultimaCuota,
    fechaCuoton: sumarMeses(operacion, MESES_CUOTON),
    filas: tablaAmortizacion(saldoFinanciar, cuotaBanco, v.cuotas, tasa, v.gracia, primeraCuota),
  };
}

const PESOS = new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 });
const FECHA = new Intl.DateTimeFormat("es-CL", { day: "2-digit", month: "2-digit", year: "numeric" });

export function pesos(valor) {
  return PESOS.format(Math.round(Math.max(0, Number(valor) || 0)));
}

export function fecha(valor) {
  return valor ? FECHA.format(valor) : "—";
}

// Texto para leerle o enviarle al cliente.
export function resumenCliente(campana, r) {
  const lineas = [
    `Simulación de renegociación – ${campana.titulo}`,
    `Cuota mensual estimada: ${pesos(r.cuota)}`,
    `Plazo: ${r.cuotas} cuota${r.cuotas === 1 ? "" : "s"}${r.gracia ? ` (${r.gracia} mes${r.gracia === 1 ? "" : "es"} de gracia)` : ""}`,
    `Primera cuota: ${fecha(r.primeraCuota)} · Última cuota: ${fecha(r.ultimaCuota)}`,
    `Tasa mensual: ${String(r.tasa).replace(".", ",")}%`,
  ];
  if (campana.code === "apoya" && r.cuoton > 0) {
    lineas.push(`Cuotón final (mes ${MESES_CUOTON}, ${fecha(r.fechaCuoton)}): ${pesos(r.cuoton)}`);
  }
  lineas.push("Valores referenciales: no constituyen una oferta formal de crédito.");
  return lineas.join("\n");
}
