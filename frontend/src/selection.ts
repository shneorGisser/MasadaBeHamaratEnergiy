import { create } from 'zustand'

/** Shared selection between the 2D schematic, the 3D bench and the readings list. */
interface SelectionState {
  selected: string | null
  select: (id: string | null) => void
}

export const useSelection = create<SelectionState>((set) => ({
  selected: null,
  select: (id) => set({ selected: id }),
}))
