interface Figure {
  data_base64: string
  format: string
  figure_num?: number
}

interface Props {
  figures: Figure[]
  title?: string
}

export default function ChartViewer({ figures, title }: Props) {
  if (!figures || figures.length === 0) return null

  return (
    <div className="flex flex-col gap-3">
      {title && <h4 className="text-sm font-medium text-gray-300">{title}</h4>}
      {figures.map((fig, i) => (
        <div
          key={i}
          className="bg-white rounded-lg overflow-hidden shadow-lg border border-gray-700"
        >
          <img
            src={`data:image/${fig.format || 'png'};base64,${fig.data_base64}`}
            alt={`Chart ${i + 1}`}
            className="w-full h-auto"
          />
        </div>
      ))}
    </div>
  )
}
