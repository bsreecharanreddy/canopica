export function CalculationMatrix({ items }: { items: { label: string; value: string }[] }) {
  return (
    <table aria-label="Calculation logic matrix" className="w-full border-collapse text-sm">
      <thead>
        <tr>
          <th
            scope="col"
            className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            Variable
          </th>
          <th
            scope="col"
            className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            Value
          </th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.label} className="border-b border-border">
            <th scope="row" className="px-3 py-2 text-left font-normal text-foreground">
              {item.label}
            </th>
            <td className="px-3 py-2 font-mono text-muted-foreground">{item.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
