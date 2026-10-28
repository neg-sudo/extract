# extract PowerShell completion
Register-ArgumentCompleter -Native -CommandName extract,x -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    $opts = '-v --verbose -l --list -f --force -d --directory -C -n --dry-run -t --test --check -i --info -r --recursive -p --password --cat --view -o --open --json --keep-junk --no-flatten --notify --insecure -j --jobs --parallel --tui -c --create --pack -q --quiet --no-color --sha256 --verify --copy-path --max-size --max-file-size --max-files --max-ratio --max-depth --include --search --grep --strict --no-exec --allow-symlinks --preserve-perms --sandbox --delete-nested --on-error --version --help'.Split(' ')
    $opts | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterName', $_)
    }
}

