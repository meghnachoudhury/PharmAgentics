/* Visual identity and SVG icon geometry. One icon set, outline style, stroke 1.6 next to 14px text.
   Always pass a size class (h-4 w-4, h-5 w-5): a className without one lets the SVG grow to fill its row. */
const PATHS={
  briefings:"M6 3h9l4 4v14H6zM9 12h7M9 16h7M9 8h3",
  send:"M5 12h14M13 6l6 6-6 6",
  evidence:"M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  close:"M6 6l12 12M18 6L6 18",
  back:"M15 18l-6-6 6-6",
  menu:"M4 7h16M4 12h16M4 17h16",
  layers:"M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17l9 5 9-5",
  chevronRight:"M9 6l6 6-6 6",
  check:"M5 12.5l4.5 4.5L19 7.5",
  pin:"M9 4h6l-1 6 3 3H7l3-3zM12 13v7",
  unpin:"M9 4h6l-1 6 3 3H7l3-3zM12 13v7M4 4l16 16",
  trend:"M4 17l5-5 4 3 7-8M15 7h5v5",
  user:"M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 20a7.5 7.5 0 0 1 15 0"
} as const
export type IconName = keyof typeof PATHS
export function Icon({name,className="h-4 w-4"}:{name:IconName,className?:string}) {
  return <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={PATHS[name]}/></svg>
}

/* The "Pa" mark (public/pa-mark.png): the product owner's artwork, with the "a" lowered like a subscript, the
   way Rx is set. The source is 64px; ask for a vector before using it larger than the sign-in card. */
const MARK={sm:"h-9 w-9",lg:"h-14 w-14"} as const
export function BrandMark({size="sm"}:{size?:keyof typeof MARK}){
  return <img src="/pa-mark.png" alt="" width={64} height={64} draggable={false} className={`shrink-0 select-none ${MARK[size]}`}/>
}
