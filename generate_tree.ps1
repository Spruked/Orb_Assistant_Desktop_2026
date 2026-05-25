$exclude = @(
    'node_modules', '__pycache__', '.venv', 'venv', '.vscode',
    'audio_cache', 'runlogs', '.git', '.orb-assistant', 'Code Cache',
    'GPUCache', 'DawnCache', 'Local Storage', 'Network', 'Session Storage',
    'blob_storage', 'leveldb', 'tests', 'results', 'test_results', 'dist'
)

$includeExt = @('.py', '.js', '.md', '.txt', '.html', '.css')

function Get-Tree {
    param(
        [string]$path,
        [string]$prefix = ""
    )

    $items = Get-ChildItem -LiteralPath $path | Where-Object {
        ($exclude -notcontains $_.Name) -and (
            $_.PSIsContainer -or (
                ($includeExt -contains $_.Extension) -and
                $_.Name -notmatch '^[a-f0-9]{64}\.json$' -and
                $_.Name -notmatch '^test_'
            )
        )
    } | Sort-Object @{ Expression = { -not $_.PSIsContainer } }, Name

    for ($i = 0; $i -lt $items.Count; $i++) {
        $item = $items[$i]
        $isLast = $i -eq ($items.Count - 1)
        $symbol = if ($isLast) { "└── " } else { "├── " }
        Write-Output "$prefix$symbol$($item.Name)"

        if ($item.PSIsContainer) {
            $newPrefix = if ($isLast) { "$prefix    " } else { "$prefix│   " }
            Get-Tree -path $item.FullName -prefix $newPrefix
        }
    }
}

Get-Tree . | Set-Content -Encoding utf8 folder_tree.txt
