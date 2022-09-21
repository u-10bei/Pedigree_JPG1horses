//hogehogeはドメイン名に置き換えてください
const LINKURL = 'https://hogehoge/PHP/StratifyLink.php'

d3.json(LINKURL)
.then(function(LINKALL){
    const data_h = d3.stratify()
    .id(function(d) { return d.From; })
    .parentId(function(d) { return d.To; })
    (LINKALL);

    const width = window.innerWidth;
    const height = window.innerHeight;

    const tree = (data) => {
        const root = d3.hierarchy(data);
        root.dx = 20;
        root.dy = width / (root.height + 1);
        return d3.tree().nodeSize([root.dx, root.dy])(root);
    };

    const root = tree(data_h);

    const zoom = d3.zoom().scaleExtent([0.5, 10]).on("zoom", zoomed);

    const svg = d3.select("#mychart")
    .append("svg")
        .attr("viewBox", [0, 0, width, height])
        .attr("cursor", "move");

    svg.call(zoom);

    const g = svg
        .append("g")
        .attr("font-family", "sans-serif")
        .attr("font-size", 12)
        .attr("transform", `translate(${root.dx * 2}, ${root.dy * 2})`);

    const link = g
        .append("g")
        .attr("fill", "none")
        .attr("stroke", "#555")
        .attr("stroke-opacity", 0.4)
        .attr("stroke-width", 1.5)
        .selectAll("path")
        .data(root.links())
        .join("path")
        .attr(
            "d",
            d3
            .linkHorizontal()
            .x((d) => d.y)
            .y((d) => d.x)
        );

    const node = g
        .append("g")
        .attr("stroke-linejoin", "round")
        .attr("stroke-width", 3)
        .selectAll("g")
        .data(root.descendants())
        .join("g")
        .attr("transform", (d) => `translate(${d.y}, ${d.x})`)
    
        node
        .append("text")
        .attr("x", d => d.children ? -5 : 5)
        .attr("dy", "0.31em")
        .attr("text-anchor", d => d.children ? "end" : "start")
        .attr("font-size", d => d.children ? (3 + Number(d.data.data.Power)) : 12)
        .text(d => d.data.id)
        .clone(true)
        .lower()
        .attr("stroke", "white");
    
        console.log(root.descendants())

        node
        .append("circle")
        .attr("fill", "#999")
        .attr("r", d => d.data.data.Value);
   
    function zoomed(event) {
        const { transform } = event;
        g.attr("transform", transform);
        g.attr("stroke-width", 1 / transform.k);
    }
});