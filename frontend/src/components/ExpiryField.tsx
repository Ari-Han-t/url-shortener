import { useId } from 'react'
import { todayInputValue, type ExpiryChoice } from '../lib/expiry'
import { inputClass } from '../lib/ui'

interface Props {
  choice: ExpiryChoice
  date: string
  onChange: (choice: ExpiryChoice, date: string) => void
  /** Edit dialogs offer "Keep current expiry"; the create form does not. */
  allowKeep?: boolean
}

export function ExpiryField({ choice, date, onChange, allowKeep }: Props) {
  const uid = useId()
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={`${uid}-expiry`} className="text-sm font-medium">
        Expires
      </label>
      <select
        id={`${uid}-expiry`}
        className={inputClass}
        value={choice}
        onChange={(e) => onChange(e.target.value as ExpiryChoice, date)}
      >
        {allowKeep && <option value="keep">Keep current</option>}
        <option value="never">Never</option>
        <option value="1">In 1 day</option>
        <option value="7">In 7 days</option>
        <option value="30">In 30 days</option>
        <option value="custom">Custom date</option>
      </select>
      {choice === 'custom' && (
        <>
          <label htmlFor={`${uid}-date`} className="sr-only">
            Expiry date
          </label>
          <input
            id={`${uid}-date`}
            type="date"
            className={inputClass}
            min={todayInputValue()}
            value={date}
            onChange={(e) => onChange(choice, e.target.value)}
          />
        </>
      )}
    </div>
  )
}
