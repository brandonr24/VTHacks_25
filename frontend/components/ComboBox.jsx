"use client"

import * as React from "react"
import { Check, ChevronsUpDown } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

const frameworks = [
  {
    value: "next.js",
    label: "Next.js",
  },
  {
    value: "sveltekit",
    label: "SvelteKit",
  },
  {
    value: "nuxt.js",
    label: "Nuxt.js",
  },
  {
    value: "remix",
    label: "Remix",
  },
  {
    value: "astro",
    label: "Astro",
  },
]

export function Combobox({ items = [], value, onChange, placeholder = "Select...", searchablePlaceholder = "Search...", widthClass = "w-[340px]" }) {
  const [open, setOpen] = React.useState(false)
  const selected = value || ""

  function handleSelect(currentValue) {
    const next = currentValue === selected ? "" : currentValue
    onChange?.(next)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={`${widthClass} justify-between truncate rounded-xl py-2`}
        >
          {selected ? (items.find((it) => it.value === selected)?.label ?? selected) : placeholder}
          <ChevronsUpDown className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className={`${widthClass} p-0`}>
        <Command>
          <CommandInput placeholder={searchablePlaceholder} className="h-9" />
          <CommandList>
            <CommandEmpty>No results.</CommandEmpty>
            <CommandGroup>
              {items.map((it) => (
                <CommandItem
                  key={it.value}
                  value={it.value}
                  onSelect={handleSelect}
                >
                  {it.label}
                  <Check
                    className={cn(
                      "ml-auto",
                      selected === it.value ? "opacity-100" : "opacity-0"
                    )}
                  />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

export default Combobox
