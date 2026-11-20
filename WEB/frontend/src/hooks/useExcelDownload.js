import { useState } from "react";
import { saveDownload } from "../utils/download";

// Boton "Descargar Excel" de las productividades: estado de carga + descarga del archivo.
// descargar(pedir, setError): pedir() devuelve { blob, filename }; los errores se muestran con setError.
export default function useExcelDownload() {
  const [descargando, setDescargando] = useState(false);

  async function descargar(pedir, setError) {
    setDescargando(true);
    setError("");
    try {
      const { blob, filename } = await pedir();
      saveDownload(blob, filename);
    } catch (err) {
      setError(err.message || "No se pudo descargar el Excel");
    } finally {
      setDescargando(false);
    }
  }

  return [descargando, descargar];
}
