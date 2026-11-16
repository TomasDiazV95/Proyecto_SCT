// Calculo del simulador de convenios Veritus (PUT / plan de pago). Solo calculo: sin React ni DOM.
// Igual que el "Constructor de plan" del portal Veritus: el monto total del convenio se reparte parejo
// entre las cuotas (mensuales desde la fecha de inicio) y la ultima absorbe el redondeo. Los limites del
// producto no bloquean: se informan como "fuera de los limites" para revision del aprobador.

import { fecha, fechaDesdeInput, pesos, sumarMeses } from "./simuladorRenegociacion";

export const CUOTA_MINIMA = 50000;

export const PRODUCTOS = {
  put: {
    code: "put",
    titulo: "PUT",
    detalle: "Pago con descuento, hasta 6 cuotas",
    icono: "bi-lightning-charge",
    maxCuotas: 6,
    descuentoMax: 50,
  },
  convenio: {
    code: "convenio",
    titulo: "Convenio",
    detalle: "Plan de pago, hasta 24 cuotas",
    icono: "bi-calendar3",
    maxCuotas: 24,
    descuentoMax: 50,
  },
};

function num(valor) {
  const n = Number(valor);
  return Number.isFinite(n) ? n : 0;
}

// Monto a pagar con un descuento sobre el saldo (redondeado al peso, como el portal).
export function montoConDescuento(saldo, descuentoPct) {
  return Math.round(num(saldo) * (1 - num(descuentoPct) / 100));
}

// Descuento que representa un monto sobre el saldo, en % con 1 decimal.
export function descuentoDeMonto(saldo, monto) {
  const s = num(saldo);
  if (s <= 0) {
    return 0;
  }
  return Math.round((1 - num(monto) / s) * 1000) / 10;
}

// Mayor numero de cuotas (dentro del producto) que deja cada cuota sobre el minimo.
export function cuotasSugeridas(producto, monto) {
  const porMinimo = Math.floor(num(monto) / CUOTA_MINIMA);
  return Math.max(1, Math.min(producto.maxCuotas, porMinimo));
}

// valores: { producto (code), saldoTotal, saldoAjustado, monto, cuotas, inicio (YYYY-MM-DD) }
export function simular(valores) {
  const producto = PRODUCTOS[valores.producto] || PRODUCTOS.convenio;
  const saldoTotal = num(valores.saldoTotal);
  const saldoAjustado = num(valores.saldoAjustado);
  const monto = Math.round(num(valores.monto));
  const cuotas = Math.floor(num(valores.cuotas));
  const inicio = fechaDesdeInput(valores.inicio);

  const erroresCampo = {};
  if (!(saldoAjustado > 0)) erroresCampo.saldoAjustado = "Ingresa el saldo de la deuda.";
  if (!(monto > 0)) erroresCampo.monto = "Ingresa el monto que pagará el cliente.";
  else if (saldoAjustado > 0 && monto > saldoAjustado) erroresCampo.monto = "No puede superar el saldo ajustado.";
  if (!(cuotas >= 1)) erroresCampo.cuotas = "Debe ser al menos 1 cuota.";
  if (!inicio) erroresCampo.inicio = "Ingresa la fecha de la primera cuota.";
  if (Object.keys(erroresCampo).length) {
    return { ok: false, producto, erroresCampo, errores: Object.values(erroresCampo) };
  }

  const base = Math.floor(monto / cuotas);
  const calendario = Array.from({ length: cuotas }, (_, i) => ({
    numero: i + 1,
    monto: i === cuotas - 1 ? monto - base * (cuotas - 1) : base,
    vencimiento: sumarMeses(inicio, i),
  }));

  const descuento = descuentoDeMonto(saldoAjustado, monto);
  const bajoMinimo = calendario.filter((c) => c.monto < CUOTA_MINIMA).length;
  const alertas = [];
  if (cuotas > producto.maxCuotas) {
    alertas.push(`El plan tiene ${cuotas} cuotas; ${producto.titulo} permite hasta ${producto.maxCuotas}.`);
  }
  if (descuento > producto.descuentoMax) {
    alertas.push(`El descuento del plan (${String(descuento).replace(".", ",")}%) supera el máximo pre-aprobado (${producto.descuentoMax}%).`);
  }
  if (bajoMinimo) {
    alertas.push(`${bajoMinimo === cuotas && cuotas > 1 ? "Todas las cuotas quedan" : `${bajoMinimo} cuota${bajoMinimo === 1 ? " queda" : "s quedan"}`} bajo el mínimo ($${CUOTA_MINIMA.toLocaleString("es-CL")}).`);
  }

  return {
    ok: true,
    producto,
    erroresCampo: {},
    errores: [],
    alertas,
    saldoTotal,
    saldoAjustado,
    monto,
    cuotas,
    cuota: base,
    ultimaMonto: calendario[cuotas - 1].monto,
    descuento,
    ahorro: Math.max(0, saldoAjustado - monto),
    primeraCuota: calendario[0].vencimiento,
    ultimaCuota: calendario[cuotas - 1].vencimiento,
    calendario,
  };
}

// Texto para leerle o enviarle al cliente.
export function resumenCliente(deudor, r) {
  const lineas = [`Simulación de convenio Veritus – ${r.producto.titulo}`];
  if (deudor) {
    lineas.push(`Cliente: ${deudor.nombre} (${deudor.rutTexto})`);
  }
  lineas.push(
    `Deuda: ${pesos(r.saldoAjustado)}`,
    `Total a pagar: ${pesos(r.monto)} (descuento ${String(r.descuento).replace(".", ",")}%, ahorro ${pesos(r.ahorro)})`,
  );
  if (r.cuotas === 1) {
    lineas.push(`Pago único: ${pesos(r.monto)} el ${fecha(r.primeraCuota)}`);
  } else {
    const ultimaDistinta = r.ultimaMonto !== r.cuota ? ` (última cuota ${pesos(r.ultimaMonto)})` : "";
    lineas.push(
      `${r.cuotas} cuotas mensuales de ${pesos(r.cuota)}${ultimaDistinta}`,
      `Primera cuota: ${fecha(r.primeraCuota)} · Última cuota: ${fecha(r.ultimaCuota)}`,
    );
  }
  lineas.push("Valores referenciales: el convenio queda sujeto a aprobación de Veritus.");
  return lineas.join("\n");
}

export function formatearRut(rut, dv) {
  return `${new Intl.NumberFormat("es-CL").format(rut)}-${dv}`;
}
