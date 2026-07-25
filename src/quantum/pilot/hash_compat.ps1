if (-not (Get-Command -Name Get-FileHash -ErrorAction SilentlyContinue)) {
    function Get-FileHash {
        [CmdletBinding(DefaultParameterSetName = "LiteralPath")]
        param(
            [Parameter(Mandatory = $true, ParameterSetName = "LiteralPath")]
            [string]$LiteralPath,

            [Parameter(Mandatory = $true, ParameterSetName = "InputStream")]
            [System.IO.Stream]$InputStream,

            [ValidateSet("SHA256")]
            [string]$Algorithm = "SHA256"
        )

        $hasher = [System.Security.Cryptography.SHA256]::Create()
        $stream = $null
        $ownsStream = $false
        try {
            if ($PSCmdlet.ParameterSetName -eq "LiteralPath") {
                $resolved = (Resolve-Path -LiteralPath $LiteralPath).Path
                $stream = [System.IO.File]::Open(
                    $resolved,
                    [System.IO.FileMode]::Open,
                    [System.IO.FileAccess]::Read,
                    [System.IO.FileShare]::Read
                )
                $ownsStream = $true
            }
            else {
                $resolved = $null
                $stream = $InputStream
            }

            $hashBytes = $hasher.ComputeHash($stream)
            $hash = ([System.BitConverter]::ToString($hashBytes)).Replace("-", "")
            return [pscustomobject]@{
                Algorithm = $Algorithm
                Hash = $hash
                Path = $resolved
            }
        }
        finally {
            if ($ownsStream -and $null -ne $stream) {
                $stream.Dispose()
            }
            $hasher.Dispose()
        }
    }
}
