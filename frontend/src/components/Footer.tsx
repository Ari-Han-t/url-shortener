const link = 'underline underline-offset-2 hover:text-ink'

export function Footer() {
  return (
    <footer className="mt-auto border-t border-line">
      <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-6 text-sm text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>
          Built by{' '}
          <a className={link} href="https://github.com/Ari-Han-t" target="_blank" rel="noreferrer">
            Arihant Gupta
          </a>
        </p>
        <a
          className={link}
          href="https://github.com/Ari-Han-t/url-shortener"
          target="_blank"
          rel="noreferrer"
        >
          Source on GitHub
        </a>
      </div>
    </footer>
  )
}
