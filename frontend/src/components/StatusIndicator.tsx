interface Props {
  status: string
}

export default function StatusIndicator({ status }: Props) {
  return (
    <div className="flex items-center gap-2 px-4 py-2 text-sm text-gray-400">
      <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
      <span>{status}</span>
    </div>
  )
}
