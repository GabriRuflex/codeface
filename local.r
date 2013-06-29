## Some local helper functions for QuantArch

## Source all r files in a given path
source.files <- function(path) {
  for (nm in list.files(path, pattern = "\\.[Rr]$")) {
    source(file.path(path, nm))
  }
}

## Create a directory if it does not yet exist
gen.dir <- function(dir) {
  if (!file_test("-d", dir)) {
    if (!dir.create(dir, recursive=TRUE)) {
      stop("Cannot create directory ", dir)
    }
  }
}

## Based on code from the snatm repository (numerical optimisation
## was added by WM)
gen.termplot <- function(edgelist, net, threshold, outfile, max.persons=NA, verbose=FALSE) {
  peoplelist <- edgelist[,1]

  exclude.list <- c() # TODO: Make this a function argument, and use it
  peoplelist <- peoplelist[!(peoplelist %in% exclude.list)]

  twomode <- net
  people <- which(is.element(rownames(twomode), unique(peoplelist)))

  if (!is.na(max.persons)) {
    ## Determine the optimal value of threshold so as to include at most
    ## max.persons persons into the network

    ## f(t) \equiv sum(rowSums(subs) > 0) is the quantity of interest: It
    ## determines how many persons will contribute to the network because they
    ## are correlated with at lest one term. By setting all values below a (to
    ## be optimised) threshold to zero, we can decrease the number of
    ## persons. So the optimisation problem is: Find threshold such that
    ## sum(rowSums(subs)) is close to max.persons, but not larger.
    ## In other words:
    ## Minimise max.persons-f(t) using t subject to f(t) <= max.persons
    ## In order to avoid the computationally more complex constrained
    ## optimisation, we simply minimise abs(max.persons-f(t)). This way,
    ## we may end up with slightly more persons then desired, but this
    ## is of no concern.
    objective <- function(thresh) {
      tmp <- twomode
      tmp[tmp < thresh] <- 0
      deg <- sna::degree(tmp, cmode="freeman")
      tmp <- tmp[,deg>0]
      tmp <- tmp[deg>0,]
      tmp <- sna::component.largest(tmp,connected="weak",result="graph")

      ## tmp can have shrunk (a lot) after applying component.largest,
      people <- which(is.element(rownames(tmp), unique(peoplelist)))
      if (verbose)
        cat("Result for threshold ", thresh, ": ", length(people), "\n")
      return (abs(max.persons - length(people)))
    }

    ## Found the optimal threshold, adapt the network accordingly
    threshold <- optimise(objective, c(0,1))
    if (verbose)
      cat("Found optimal threshold ", threshold$minimum)
    twomode[twomode < threshold$minimum] <- 0
  } else {
    twomode[twomode < threshold] <- 0
  }

  deg <- sna::degree(twomode, cmode="freeman")
  twomode <- twomode[,deg>0]
  twomode <- twomode[deg>0,]
  twomode <- sna::component.largest(twomode,connected="weak",result="graph")
  deg <- sna::degree(twomode)

  labelcol <- rep(rgb(0,0,1,0.75),dim(twomode)[1])
  
  ## component.largest shrinks the adjacency matrix, so we need to recompute
  ## the people list indices
  people <- which(is.element(rownames(twomode), unique(peoplelist)))

  labelcol[people] <- "red"
  pdf(file=outfile)
  par(mar=c(0,0,0,0))
  gplot.snatm(twomode
              ,gmode="graph"
              ,vertex.col="white"
              ,vertex.cex=1
              ,label=rownames(twomode)
              ,label.col=labelcol
              ,label.cex=(deg^0.25)*0.35
              ,label.pos=5
              ,boxed.labels=FALSE
              ,edge.lwd=0.1
              ,vertex.border="white"
              ,edge.col="grey")
  dev.off()
}

## TODO: Do something with the sizes output of edgelist (which describes the weight
## of each keyword), for instance visualise the distribution as a sanity indicator
gen.net <- function(type, termfreq, data.path, max.terms) {
  if (!(type %in% c("subject", "content"))) {
    stop ("Please specify either 'subject' or 'content' for type")
  }
  res <- centrality.edgelist(termfreq, type, data.path, max.terms)
  net <- adjacency(res[[1]], mode="addvalues", directed=F)
  
#  print(ggplot(data.frame(x=res[[2]]), aes(x=x)) + geom_histogram(binwidth=1))
  return(list(res[[1]], net))
}

## When a mail without properly specified author is encountered, the
## name is mapped to NA, which leads to NAs in several of the networks.
## Get rid of these entries since they don't carry accurate information
fixup.network <- function(.net) {
  idx <- !is.na(colnames(.net))

  return(.net[idx, idx])
}

## Fix some common problems that appear in mailing list author
## specifications.
fixup.authors <- function(authors) {
  authors <- gsub(pattern='"', x=authors, replacement="")
  authors <- gsub(pattern=" via [[:print:]]*>?|\\]?", x=authors,
                  replacement="")

  authors[authors==""] <- NA
  return(authors)
}

## Author name normalisation. Replace the name/email pairs found in
## the messages with a decomposed name and a unique in-database ID
do.normalise <- function(conf, authors) {
  authors <- fixup.authors(authors)

  authorIDs <- sapply(authors, function(namestr) {
    if (is.na(namestr)) {
      return(NA)
    }

    return(query.decompose.user.id(conf, namestr))
  })

  authors.names <- sapply(authorIDs, function(author.id) {
    return(query.person.name(conf$con, author.id))
  })

  return(list(authorIDs=authorIDs, authors=authors.names))
}

## Method is adapted from snatm. The function defined there seems wrong -- the
## centrality index is always scaled to [0,1], even if, say, only the first
## part of the interval is populated, and the second part consists solely of NAs
## (because there are no persons of high centrality in the network)
gen.networks.df <- function(networks) {
  ## For each centrality measure, compute a mapping from centrality to correlation:
  ## Given a desired centrality c, select only the adjacency matrix entrie that
  ## exceed c from the interest and communication networks. Then, re-arrange the numbers
  ## into a vector and compute the correlation between the vectors. If the
  ## correlation is large, then the same authors appear in both facedes of the
  ## networks
  interestnet <- networks[[1]]
  network.red <- networks[[2]]
  cty.list <- networks[[3]]
  ret <- NULL
  
  for (cty.idx in seq_along(cty.list)) {
    ## NOTE: cty = centrality
    cty.values <- seq(0, max(cty.list[[cty.idx]]), length.out=100)

    ## NOTE: The paper by Bohn et al. uses correlation as distance measure;
    ## since this can become negative, it does not seem to be the easiest to
    ## interpret choice.  The cosine distance, on the other hand, is
    ## normalised on [0,1] (see the proxy package for alternative distance
    ## measures)
#    distfn <- cor
    distfn <- cosine
    
    compute.similarity <- function(cty.minval) {
      data.frame(dist=distfn(as.vector(interestnet[cty.list[[cty.idx]] >= cty.minval,
                                                   cty.list[[cty.idx]] >= cty.minval]),
                             as.vector(network.red[cty.list[[cty.idx]] >= cty.minval,
                                                   cty.list[[cty.idx]] >= cty.minval])),
                 centrality=cty.minval/max(cty.list[[cty.idx]]))
    }

    tmp <- do.call(rbind, lapply(cty.values, compute.similarity))
    ret <- rbind(ret, cbind(as.data.frame(tmp), type=names(cty.list[cty.idx])))
  }

  ret$type <- as.factor(ret$type)
  return(ret)
}

## Find terms with highest relative frequency (given by percentage).
## However, the result set can be limited to max.entries entries unless
## max.entries=-1.
## If min.entries is =! -1, this many terms are collected if possible
## exclude.list specifies a list of generic keywords that are not supposed to
## be considered.
findHighFreq <- function(x, percentage=0.1, min.entries=-1, max.entries=50,
                         exclude.list=list()) {
  if (inherits(x, "DocumentTermMatrix")) 
        x <- t(x)
  tmp <- sort(slam::row_sums(x), decreasing=T)

  rs <- names(tmp)
  names(rs) <- tmp

  ## Delete unwanted terms
  rs <- rs[!(rs %in% exclude.list)]

  ## ... and shorten the results list by percentage and upper bound
  num <- floor(length(rs)*percentage)
  if (max.entries != -1 && num > max.entries) {
    num <- max.entries
  }

  if (min.entries != -1 && num < min.entries) {
    num <- min.entries
  }

  if (length(rs) > num)
    rs <- rs[1:num]

  return(rs)
}

## Compute the interest network (adapted from the snatm paper)
## TODO: Get rid of the indexing crap and use named lists
gen.cmp.networks <- function(basenets, commnet) {
  people <- which(is.element(rownames(basenets[[2]]), unique(basenets[[1]][,1])))
  interestnet <- shrink(basenets[[2]], by="row", keep=people, values="min")
  
  commnet <- fixup.network(commnet)
  interestnet <- fixup.network(interestnet)

  ## Remove any persons from commnet that are contained in interestnet, but not
  ## in commnet.
  ## This can happen if some wrote a single mail in a given time period
  ## (the person then has interests, but did not communicate with
  ## anyone). Especially, this can occur if a thread is cut off by temporal
  ## sub-span selection.
  ## TODO: In general, the complete approach to network selection seems clumsy
  ## and should be refactored.
  network.red <- commnet[is.element(rownames(commnet), rownames(interestnet)),
                         is.element(rownames(commnet), rownames(interestnet))]

  ## Same operation with the roles of both networks reversed
  interestnet <- interestnet[is.element(rownames(interestnet), rownames(commnet)),
                             is.element(rownames(interestnet), rownames(commnet))]

  ## Permute the communication network such that the order
  ## of elements is identical to the interest network
  network.red <- permutation(network.red, rownames(interestnet))

  ## TODO: Why are different packages used to compute the graph measures?
  ## They should all be supported by SNA
  network.red.ig <- graph.adjacency(network.red, mode="directed")
  deg <- sna::degree(network.red, cmode="freeman", gmode="graph", ignore.eval=TRUE)
  betw <- igraph::betweenness(network.red.ig, directed=F)
  clo <- igraph::closeness(network.red.ig)
  cty.list <- list(deg, betw, clo)
  names(cty.list) <- c("Degree", "Betweenness", "Closeness")

  return(list(interestnet, network.red, cty.list))
}


### Initiating threads vs. replying. Adapted from the snatm repository ###
## network.red denotes the members of the network; cty.list is a list of
## three vertex characteristics measures (Degree, Betweenness, Closeness)
DEG.THRESHOLD <- 0.3 ## Threshold above which to mark vertices as highly central
compute.initiate.respond <- function(forest, network.red, cty.list) {
  ir <- initiate.respond(forest)

  cent <- na.omit(data.frame(name=rownames(network.red), responses=0,
                             initiations=0, deg=cty.list$Degree,
                             col="Low deg"))
  cent$col <- factor(cent$col, levels=c("Low deg", "High deg"))
  cent$name <- as.character(cent$name)

  ## For each name that appears in network.red, select the fitting
  ## entry from the initiate.respond list, and connect both per
  ## person-statistics (number of initiations/responses and degree)
  for (i  in seq_along(cent$name)) {
    ir.idx <- which(ir$name == cent$name[i])

    if (length(ir.idx) != 1) {
      stop("Internal error: Name from communication network not in ",
           "initiate.response list")
    }

    cent$responses[i] <- ir$responses[ir.idx]
    cent$initiations[i] <- ir$initiations[ir.idx]
  }


  ## TODO: Why does snatm want to construct an outlier here?! 
##  cent[dim(cent)[1],] <- c(max(cent[,1])+40, max(cent[,2])+100, 0)
  cent$deg <- normalize(cent$deg)
  cent$col[cent$deg > DEG.THRESHOLD] <- "High deg"

  return(cent)
}

construct.intervals <- function(date.start, date.end, interval.length) {
  ## Given a start and end date, compute a list of intervals of
  ## length interval.length (given in weeks) that span the date range.

  t.start <- ceiling_date(date.start, "week")
  num.intervals <- floor((date.end-t.start)/dweeks(interval.length))
  if (num.intervals < 1) {
    ## Pathological case for repositories that encompass less
    ## than one full interval
    num.intervals <- 1
  }

  boundaries <- t.start + c(0:num.intervals)*dweeks(interval.length)

  ## Transform the boundaries into a list of intervals. These can then be
  ## directly utilised by lapply, leading to an easy prey for parallelisation
  intervals.list <- lapply(1:(length(boundaries)-1),
                           function(i) new_interval(boundaries[i],
                                                    boundaries[i+1]))
  return (intervals.list)
}


get.nonempty.intervals <- function(dates, intervals.list) {
  ## Given a list of dates (typically representing dates of messages)
  ## and a list of intervals, determine which of the intervals
  ## contain less than MIN.NUM.MESSAGES messages, and remove them
  ## from the list -- they are considered outliers.
  ## This is the reason why not just the date boundaries, but a complete
  ## list of dates is required as input.
  MIN.NUM.MESSAGES <- 5
  if (length(dates) == 0)
    stop("Date list for interval generation is empty!")

  ## An archive can contain messages with bogous time stamps. Such
  ## outliers can increase the time range of all messages considerably,
  ## and will consequently leave many intervals completely empty
  ## (consider a dense interval from 01.05. to 31.07, with one outlier
  ## in the 1.1. The range 01.01 -- 31.04 will formally exist, but be empty)
  ## Detect essentially empty ranges (with less than 5 messages) and remove
  ## them from the interval list
  msg.per.interval <- function(timestamps, itv) {
    idx <- which(timestamps >= int_start(itv) &
                 timestamps < int_end(itv))
    return(length(timestamps[idx]))
  }
  idx <- sapply(intervals.list, function(i) msg.per.interval(dates, i))

  return(which(idx >= MIN.NUM.MESSAGES))
}

## Frontend for the above functions: Take a list of dates and
## an interval length, and computer a list of non-empty intervals
gen.iter.intervals <- function(dates, interval.length) {
  intervals.list <- construct.intervals(min(dates), max(dates), interval.length)

  return (intervals.list[get.nonempty.intervals(dates, intervals.list)])
}

## Aggregate by hours and a daily rolling mean (the mailing list
## data do not contain excessive outliers, so mean is sufficient)
gen.agg.smooth.ts <- function(ts, smooth) {
  ts.as <- ts # In case rollmean fails
  try(ts.as <- rollmean(period.apply(ts, INDEX=endpoints(ts, 'hours'),
                                     FUN=sum), smooth))
  ts.df <- data.frame(date=index(ts.as), value=coredata(ts.as), smooth=smooth)
}
