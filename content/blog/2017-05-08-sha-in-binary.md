Title: Stamping Git SHAs into Your Binaries
Slug: sha-in-binary

Have you ever looked at a binary from a project you wrote and asked, "Where the hell
are the sources for this?" Well, I'm about to make your life (and the lives of your
customers) a bit easier. I'm going to show you how to write the Git SHA1 for each
commit directly into the resulting binaries.

If your build is anything like Roslyn you may have a half dozen different branches,
each with their own little modifications, each of which get built occasionally for
testing or prerelease validation. Often I'll find Roslyn binaries randomly floating
in a share somewhere or attached to a bug report with little to no context. While
we do have carefully incremented version numbers in our builds, it can be a challenge
to even reverse engineer a version into a specific source code commit. If each branch
doesn't have its own versioning scheme it's possible that two branches could
produce binaries with the exact same version, even if they came from completely
different source code. Solution: write the commit SHA directly into the binary. Then
you'll always know exactly what code was used to build the binary. This
guide will be targeted at people building .NET applications, but I'll give general
advice where applicable and you can choose what makes sense for your build.

The first question is, where in the binary do we write the SHA? My answer is: wherever
it's easiest to see. For console programs, that may mean including the SHA in the output
from a `--version` flag. For most programs, I think the file metadata, as displayed by
a common file system browser on your preferred OS, is the most accessible tag. Specifically,
for .NET programs I like using the `AssemblyInformationalVersionAttribute`. This tag

  1. Is only specified as a block of text, making it perfect for human-readable unstructured
     data.
  2. Is viewable by default in the Windows File Explorer both in the file listing view
     and in the properties window.
  3. Is easily accessible by .NET code via reflection.

Here's what it looks like in File Explorer with details expanded:

![File explorer screenshot]({static}/images/file-xplore.jpg)

For Unix-like systems I would probably try to use extended file attributes, although
an exact analog is hard to come by because this is not exactly standardized across POSIX
systems.

Once you've figured out where to put the SHA, you need to retrieve the SHA in the first
place. Now I know what you're thinking: "well that's easy, I'll just shell out to git
and run a quick `git rev-parse HEAD`...". Nuh-uh. Let's assume that Git is installed on
the machine&mdash;what makes you think it's available on the path? As I found out quite
quickly when I implemented this for Roslyn, there are a lot of instances where someone
may be building your code (like in a build lab) that checks out the Git repository, but
doesn't build with Git on the path. Instead, I found that the most robust method is to
either pass the SHA through an environment variable generated by the build environment,
or to grab the SHA directly out of the Git object directory. Don't worry, I won't leave you flailing;
here's the Roslyn MSBuild logic for finding and reading the
Git SHA (sorry about the XML).

    :::xml
    <When Condition="'$(BUILD_SOURCEVERSION)' != ''">
      <PropertyGroup>
        <GitHeadSha>$(BUILD_SOURCEVERSION)</GitHeadSha>
      </PropertyGroup>
    </When>
    <When Condition="'$(BUILD_SOURCEVERSION)' == '' AND '$(GIT_COMMIT)' != ''">
      <PropertyGroup>
        <GitHeadSha>$(GIT_COMMIT)</GitHeadSha>
      </PropertyGroup>
    </When>
    <Otherwise>
      <PropertyGroup>
        <GitHeadSha>Not found</GitHeadSha>
        <DotGitDir>$([System.IO.Path]::GetFullPath('$(MSBuildThisFileDirectory)../../.git'))</DotGitDir>
        <HeadFileContent Condition="Exists('$(DotGitDir)/HEAD')">$([System.IO.File]::ReadAllText('$(DotGitDir)/HEAD').Trim())</HeadFileContent>
        <RefPath Condition="$(HeadFileContent.StartsWith('ref: '))">$(DotGitDir)/$(HeadFileContent.Substring(5))</RefPath>
        <GitHeadSha Condition="'$(RefPath)' != '' AND Exists('$(RefPath)')">$([System.IO.File]::ReadAllText('$(RefPath)').Trim())</GitHeadSha>
        <GitHeadSha Condition="'$(HeadFileContent)' != '' AND '$(RefPath)' == ''">$(HeadFileContent)</GitHeadSha>
      </PropertyGroup>
    </Otherwise>

It's  a little verbose, but should be pretty straight-forward. We first try to
read the SHA directly out of the refs file in `.git/HEAD` prefixed with the
text `ref: `. Otherwise we assume a format called a ["packed
ref"](https://git-scm.com/docs/git-pack-refs), on which I won't go into detail
here. It's basically a pointer to another file, so we just read the new
file and use the content from the second file. Afterwards, the `GitHeadSha`
param is passed to `<AssemblyInformationalVersionAttribue>`, where it flows
into the binary.

With that I'll leave you to try this yourself, and hopefully your days of playing source-code-detective are over.