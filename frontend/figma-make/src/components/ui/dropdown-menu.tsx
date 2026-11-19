// shadcn/ui-style dropdown menu on Radix (keyboard navigation, focus return, typeahead, Escape), themed with
// the app's tokens. Only the parts the account menu uses.
import * as Menu from "@radix-ui/react-dropdown-menu"
import type { ComponentPropsWithoutRef } from "react"

export const DropdownMenu = Menu.Root
export const DropdownMenuTrigger = Menu.Trigger

export function DropdownMenuContent({ className = "", sideOffset = 8, ...props }: ComponentPropsWithoutRef<typeof Menu.Content>) {
  return <Menu.Portal>
    <Menu.Content sideOffset={sideOffset} collisionPadding={12}
      className={`z-50 min-w-[16rem] overscroll-contain glass rounded-xl p-1.5 text-ink shadow-2xl shadow-black/50 border border-rule pa-rise ${className}`} {...props} />
  </Menu.Portal>
}

export function DropdownMenuItem({ className = "", ...props }: ComponentPropsWithoutRef<typeof Menu.Item>) {
  return <Menu.Item className={`flex cursor-pointer select-none items-center gap-2 rounded-lg px-3 py-2 text-sm outline-none transition data-[highlighted]:bg-paper data-[disabled]:opacity-50 ${className}`} {...props} />
}

export function DropdownMenuLabel({ className = "", ...props }: ComponentPropsWithoutRef<typeof Menu.Label>) {
  return <Menu.Label className={`px-3 py-2 ${className}`} {...props} />
}

export function DropdownMenuSeparator({ className = "", ...props }: ComponentPropsWithoutRef<typeof Menu.Separator>) {
  return <Menu.Separator className={`my-1.5 h-px bg-rule ${className}`} {...props} />
}

export const DropdownMenuRadioGroup = Menu.RadioGroup

export function DropdownMenuRadioItem({ className = "", children, ...props }: ComponentPropsWithoutRef<typeof Menu.RadioItem>) {
  return <Menu.RadioItem className={`flex cursor-pointer select-none items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm outline-none transition data-[highlighted]:bg-paper data-[state=checked]:text-agentdeep ${className}`} {...props}>
    {children}
    <Menu.ItemIndicator><svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg></Menu.ItemIndicator>
  </Menu.RadioItem>
}
