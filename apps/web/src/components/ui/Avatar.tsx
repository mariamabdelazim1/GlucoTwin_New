export function Avatar({ label, size = 'md' }: { label: string; size?: 'sm' | 'md' | 'lg' }) {
  const sizes = { sm: 'h-8 w-8 text-xs', md: 'h-10 w-10 text-sm', lg: 'h-14 w-14 text-lg' };
  return (
    <div className={`${sizes[size]} grid shrink-0 place-items-center rounded-full bg-clinical-secondary font-bold text-clinical-primaryDark`} aria-hidden="true">
      {label}
    </div>
  );
}
