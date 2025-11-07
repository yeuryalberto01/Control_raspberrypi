export async function confirmAction(message: string): Promise<boolean> {
  const typed = window.prompt(`${message}\n\nEscribe CONFIRMAR para continuar:`);
  return typed?.trim().toUpperCase() === "CONFIRMAR";
}
