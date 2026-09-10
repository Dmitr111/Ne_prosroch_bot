/** Переключатель «Продукты / Рекомендации» из макетов 2.4 и 2.5. */

export type Tab = 'products' | 'recommendations'

interface TabsProps {
  active: Tab
  onChange: (tab: Tab) => void
}

export function Tabs({ active, onChange }: TabsProps) {
  return (
    <div className="tabs" role="tablist">
      <button
        role="tab"
        aria-selected={active === 'products'}
        className={`tabs__item ${active === 'products' ? 'tabs__item--active' : ''}`}
        onClick={() => onChange('products')}
      >
        Продукты
      </button>
      <button
        role="tab"
        aria-selected={active === 'recommendations'}
        className={`tabs__item ${
          active === 'recommendations' ? 'tabs__item--active' : ''
        }`}
        onClick={() => onChange('recommendations')}
      >
        Рекомендации
      </button>
    </div>
  )
}
