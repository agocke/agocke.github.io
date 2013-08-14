--------------------------------------------------------------------------------
{-# LANGUAGE OverloadedStrings #-}
import           Control.Applicative ((<$>))
import           Data.Monoid         (mappend)
import           Hakyll
import           GHC.IO.Encoding

--------------------------------------------------------------------------------
main :: IO ()
main = do
      setLocaleEncoding utf8
      setFileSystemEncoding utf8
      setForeignEncoding utf8
      hakyll $ do
      match "images/*" $ do
          route   idRoute
          compile copyFileCompiler

      match "css/*" $ do
          route   idRoute
          compile compressCssCompiler

      match "about.markdown" $ do
          route   $ setExtension ".html"
          compile $ pandocCompiler
              >>= loadAndApplyTemplate "templates/default.html" defaultContext
              >>= relativizeUrls

      match "welcome.markdown" $ do
          route   $ constRoute "index.html"
          compile $ pandocCompiler
              >>= loadAndApplyTemplate "templates/default.html" defaultContext
              >>= relativizeUrls

      match "posts/*" $ do
          route $ setExtension "html"
          compile $ pandocCompiler
              >>= loadAndApplyTemplate "templates/post.html"    postCtx
              >>= loadAndApplyTemplate "templates/default.html" postCtx
              >>= relativizeUrls

      create ["archive.html"] $ do
          route idRoute
          compile $ do
              let archiveCtx =
                      field "posts" (\_ -> postList recentFirst) `mappend`
                      constField "title" "Archives"              `mappend`
                      defaultContext

              makeItem ""
                  >>= loadAndApplyTemplate "templates/archive.html" archiveCtx
                  >>= loadAndApplyTemplate "templates/default.html" archiveCtx
                  >>= relativizeUrls

      match "templates/*" $ compile templateCompiler

--------------------------------------------------------------------------------
postCtx :: Context String
postCtx =
    dateField "date" "%B %e, %Y" `mappend`
    defaultContext


--------------------------------------------------------------------------------
postList :: ([Item String] -> [Item String]) -> Compiler String
postList sortFilter = do
    posts   <- sortFilter <$> loadAll "posts/*"
    itemTpl <- loadBody "templates/post-item.html"
    list    <- applyTemplateList itemTpl postCtx posts
    return list
