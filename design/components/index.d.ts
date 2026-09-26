import type * as React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** secondary is the default. primary at most once per view. danger for withdraw/archive. */
  variant?: 'primary' | 'secondary' | 'quiet' | 'danger';
  size?: 'md' | 'lg';
  /** An inline stroke SVG, 18px, currentColor. */
  icon?: React.ReactNode;
}
export declare function Button(props: ButtonProps): React.ReactElement;

export interface FilterPillProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  pressed?: boolean;
}
export declare function FilterPill(props: FilterPillProps): React.ReactElement;

export interface SearchFieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Accessible name. Default "Search the catalogue". */
  label?: string;
}
export declare function SearchField(props: SearchFieldProps): React.ReactElement;

export interface NavItemProps {
  href?: string;
  current?: boolean;
  /** Short count or status on the right: "32", "4 out". */
  count?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}
export declare function NavItem(props: NavItemProps): React.ReactElement;

export interface StatusChipProps {
  /** shelf = good (ledger-blue), loan = on loan or in progress (sepia), warn = attention (oxblood), neutral. */
  tone?: 'shelf' | 'loan' | 'warn' | 'neutral';
  dot?: boolean;
  children?: React.ReactNode;
  className?: string;
}
export declare function StatusChip(props: StatusChipProps): React.ReactElement;

export interface StickerProps {
  /** low → "L" on oxblood; dry → "D" on ink. */
  kind: 'low' | 'dry';
  className?: string;
}
export declare function Sticker(props: StickerProps): React.ReactElement;

export interface DateStampProps {
  /** Degrees, default -2. Vary between -2 and 2 down a list. */
  tilt?: number;
  children?: React.ReactNode;
  className?: string;
}
export declare function DateStamp(props: DateStampProps): React.ReactElement;

export interface MeterProps {
  /** Grams remaining. */
  value: number;
  /** Net grams on a full spool. Default 1000. */
  max?: number;
  /** Text before the percentage, e.g. "≈ 205 m". */
  aside?: string;
  label?: string;
  className?: string;
}
export declare function Meter(props: MeterProps): React.ReactElement;

export interface SwatchProps {
  /** Filament colour as #rrggbb. */
  hex: string;
  size?: 'sm' | 'md' | 'lg';
  /** Accessible name; omit when the colour name is written next to it. */
  label?: string;
  className?: string;
}
export declare function Swatch(props: SwatchProps): React.ReactElement;

export interface SpoolDrawingProps {
  hex: string;
  /** Grams remaining. */
  remaining: number;
  /** Net grams on a full spool. Default 1000. */
  net?: number;
  /** Pixel size of the square drawing. Default 300. */
  size?: number;
  className?: string;
}
export declare function SpoolDrawing(props: SpoolDrawingProps): React.ReactElement;

export interface SpoolSpineProps {
  /** Four-digit accession number, e.g. "0142". */
  no: string;
  /** Colour name, short enough to fit the spine: "Cobalt Blue". */
  name: string;
  material?: string;
  hex: string;
  /** Override the automatic white/ink label colour. */
  fg?: string;
  grams?: number;
  flag?: 'low' | 'dry';
  /** 40–54px. Default 44. */
  width?: number;
  /** 132–158px. Default 148. */
  height?: number;
  /** When set, the spine is a link to the spool's record. */
  href?: string;
  className?: string;
}
export declare function SpoolSpine(props: SpoolSpineProps): React.ReactElement;

export interface ShelfProps {
  name: string;
  /** "Dry box 1 · PLA · 18% RH · 14 spools" */
  meta?: string;
  /** Colour the meta line oxblood (humidity too high). */
  warn?: boolean;
  /** A link on the right of the header. */
  action?: React.ReactNode;
  /** SpoolSpine elements. */
  children?: React.ReactNode;
  className?: string;
}
export declare function Shelf(props: ShelfProps): React.ReactElement;

export interface IndexCardProps {
  /** "No. 0142 · Shelf A · Dry box 1" */
  accession: string;
  title: string;
  subtitle?: string;
  status?: string;
  statusTone?: StatusChipProps['tone'];
  /** Label/value pairs, laid out two columns wide. */
  fields?: Array<[string, React.ReactNode]>;
  /** Content between the header and the fields, usually a Meter. */
  children?: React.ReactNode;
  className?: string;
}
export declare function IndexCard(props: IndexCardProps): React.ReactElement;

export interface SlotSpool {
  no: string;
  name: string;
  material: string;
  hex: string;
  /** "Tue 22 Sep" */
  since: string;
  used: number;
  left: number;
}
export interface SlotCardProps {
  /** "AMS 1", "External" */
  slot: string;
  /** Omit for a free slot. */
  spool?: SlotSpool;
  inUse?: boolean;
  onReturn?: () => void;
  onLend?: () => void;
  className?: string;
}
export declare function SlotCard(props: SlotCardProps): React.ReactElement;

export interface BookplateProps {
  no: string;
  name: string;
  subtitle?: string;
  /** Short printing facts, e.g. ["190–230 °C", "Bed 35–45 °C", "Tare 250 g"]. */
  specs?: string[];
  acquired?: string;
  /** A real QR code element; defaults to a labelled placeholder. */
  qr?: React.ReactNode;
  className?: string;
}
export declare function Bookplate(props: BookplateProps): React.ReactElement;

/** White or ink, whichever reads better on a filament colour. */
export declare function inkOn(hex: string): string;

declare global {
  interface Window {
    Filamentarium: {
      Button: typeof Button; FilterPill: typeof FilterPill; SearchField: typeof SearchField; NavItem: typeof NavItem;
      StatusChip: typeof StatusChip; Sticker: typeof Sticker; DateStamp: typeof DateStamp; Meter: typeof Meter;
      Swatch: typeof Swatch; SpoolDrawing: typeof SpoolDrawing; SpoolSpine: typeof SpoolSpine; Shelf: typeof Shelf;
      IndexCard: typeof IndexCard; SlotCard: typeof SlotCard; Bookplate: typeof Bookplate; inkOn: typeof inkOn;
    };
  }
}
