// UI-layout contract: layer controls are always visible and never change scene height.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'..','web','stage_2_raw_player.html'),'utf8');
const reviewLayers=fs.readFileSync(path.join(__dirname,'..','web','stage_2_review_layers.js'),'utf8');

test('review controls are a permanently visible fixed-height sidebar, not a disclosure in header flow',()=>{
  assert.doesNotMatch(html,/<details\s+id=["']review-tools["']/,
    'opening review controls must not change header height or shrink the point-cloud scene');
  assert.match(html,/<aside\s+id=["']review-tools["'][^>]*>/,
    'review controls must be a dedicated persistent sidebar');
  assert.match(html,/#workspace\s*\{[^}]*grid-template-columns:/,
    'sidebar and point-cloud scene require an explicit stable layout');
  assert.match(html,/#scene\s*\{[^}]*min-height:0/,
    'the scene must occupy the available workspace height instead of header-flow remainder');
  for(const noise of ['Для оси выберите точки двух головок рельсов',
    'Автоматическая гипотеза только кадра', 'Стороны — по направлению от ближней пары',
    'Пол/рельсы не удаляются и могут давать пересечения', 'Полоса поиска X ±1,9 м',
    'Сохранённые результаты рассчитаны по прежней геометрии',
    'Исходные XYZ · один кадр, без накопления'])
    assert.doesNotMatch(html, new RegExp(noise), 'sidebar must not contain verbose diagnostic copy');
  assert.doesNotMatch(reviewLayers, /Автоось:/,
    'a successful automatic axis must not add an unexplained diagnostic range to the header');
  for(const id of ['axis-info','live-status','object-status','live-details','object-info','annotations','layer-info'])
    assert.match(html, new RegExp(`id=["']${id}["'][^>]*hidden`), `${id} stays available to scripts but hidden from sidebar`);
});
