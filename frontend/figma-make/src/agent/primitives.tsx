/* Visual identity and SVG icon geometry retained from the original Make export.
   No review-state or provenance components are included because their backend
   capabilities do not exist in the current Briefing API. */
const PATHS={
  briefings:"M6 3h9l4 4v14H6zM9 12h7M9 16h7M9 8h3",
  send:"M5 12h14M13 6l6 6-6 6",
  evidence:"M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  close:"M6 6l12 12M18 6L6 18",
  back:"M15 18l-6-6 6-6",
  menu:"M4 7h16M4 12h16M4 17h16",
  layers:"M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17l9 5 9-5",
  chevronRight:"M9 6l6 6-6 6"
} as const
export function Icon({name,className="h-4 w-4"}:{name:keyof typeof PATHS,className?:string}) {
  return <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={PATHS[name]}/></svg>
}
const MARK={sm:["h-9 w-9 rounded-xl","h-5 w-5"],lg:["h-14 w-14 rounded-2xl","h-7 w-7"]} as const
export function BrandMark({size="sm"}:{size?:keyof typeof MARK}){
 const [box,icon]=MARK[size]
 return <span className={`grid shrink-0 place-items-center bg-linear-to-br from-agent to-agentdeep text-white shadow-sm ${box}`}><Icon name="layers" className={icon}/></span>
}
